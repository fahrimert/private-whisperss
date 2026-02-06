package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/streadway/amqp"
)

var (
	OllamaURL = "http://pw-ollama:11434" 
	QdrantURL = os.Getenv("QDRANT_URL")
)


type Job struct {
	ID       string `json:"job_id"`
	FilePath string `json:"file_path"`
	Status   string `json:"status"`
}

type ChatRequest struct {
	Question string `json:"question"`
}

type EmbeddingRequest struct {
	Model  string `json:"model"`
	Prompt string `json:"prompt"`
}
type EmbeddingResponse struct {
	Embedding []float64 `json:"embedding"`
}

type QdrantSearchRequest struct {
	Vector      []float64 `json:"vector"`
	Limit       int       `json:"limit"`
	WithPayload bool      `json:"with_payload"`
}
type QdrantSearchResponse struct {
	Result []struct {
		Score   float64 `json:"score"`
		Payload struct {
			Summary  string `json:"summary"`
			FilePath string `json:"file_path"`
		} `json:"payload"`
	} `json:"result"`
}

type GenerateRequest struct {
	Model  string `json:"model"`
	Prompt string `json:"prompt"`
	Stream bool   `json:"stream"`
}
type GenerateResponse struct {
	Response string `json:"response"`
}

func main() {
	if QdrantURL == "" {
		QdrantURL = "http://qdrant:6333"
	}

	var conn *amqp.Connection
	var err error
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		rabbitURL = "amqp://guest:guest@rabbitmq:5672/"
	}

	for i := 0; i < 10; i++ {
		conn, err = amqp.Dial(rabbitURL)
		if err == nil {
			fmt.Println("✅ RabbitMQ'ya bağlanıldı!")
			break
		}
		fmt.Printf("⏳ RabbitMQ bekleniyor (%d/10)...\n", i+1)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		log.Fatal("RabbitMQ bağlantı hatası:", err)
	}
	defer conn.Close()

	ch, _ := conn.Channel()
	defer ch.Close()

	q, _ := ch.QueueDeclare(
		"task_queue",
		true,
		false, false, false, nil,
	)

	app := fiber.New()

	os.Mkdir("./uploads", 0755)

	app.Post("/upload", func(c *fiber.Ctx) error {
		file, err := c.FormFile("file")
		if err != nil {
			return c.Status(400).SendString("Dosya yüklenemedi")
		}

		id := uuid.New().String()
		filePath := fmt.Sprintf("./uploads/%s_%s", id, file.Filename)

		if err := c.SaveFile(file, filePath); err != nil {
			return c.Status(500).SendString("Dosya kaydedilemedi")
		}

		job := Job{ID: id, FilePath: filePath, Status: "queued"}
		body, _ := json.Marshal(job)

		err = ch.Publish(
			"",
			q.Name,
			false, false,
			amqp.Publishing{
				ContentType: "application/json",
				Body:        body,
			})

		if err != nil {
			return c.Status(500).SendString("Kuyruğa atılamadı")
		}

		fmt.Printf("📨 Görev Kuyruğa Atıldı: %s\n", id)
		return c.JSON(fiber.Map{
			"status":  "accepted",
			"job_id":  id,
			"message": "Dosya işlenmek üzere sıraya alındı.",
		})
	})

	app.Post("/chat", func(c *fiber.Ctx) error {
		var req ChatRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "Geçersiz istek gövdesi"})
		}

		fmt.Printf("🔎 Soru Geldi: %s\n", req.Question)

		vector, err := getEmbedding(req.Question)
		if err != nil {
			return c.Status(500).JSON(fiber.Map{"error": "Vektör oluşturma hatası: " + err.Error()})
		}

		contextText, sources, err := searchQdrant(vector)
		if err != nil {
			fmt.Printf("⚠️ Qdrant Hatası (veya sonuç yok): %v\n", err)
		}

		prompt := fmt.Sprintf(`
		You are a helpful AI assistant. Use the following CONTEXT (summaries of audio files) to answer the QUESTION.
		If the answer is not in the context, say "I don't have enough information."
		
		CONTEXT:
		%s
		
		QUESTION: 
		%s
		
		ANSWER:`, contextText, req.Question)

		answer, err := generateResponse(prompt)
		if err != nil {
			return c.Status(500).JSON(fiber.Map{"error": "Ollama cevap hatası: " + err.Error()})
		}

		return c.JSON(fiber.Map{
			"answer":  answer,
			"sources": sources,
		})
	})

	log.Fatal(app.Listen(":8080"))
}


func getEmbedding(text string) ([]float64, error) {
	payload := EmbeddingRequest{
		Model:  "all-minilm", 
		Prompt: text,
	}
	jsonData, _ := json.Marshal(payload)

	resp, err := http.Post(OllamaURL+"/api/embeddings", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result EmbeddingResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return result.Embedding, nil
}

func searchQdrant(vector []float64) (string, []string, error) {
	payload := QdrantSearchRequest{
		Vector:      vector,
		Limit:       3,
		WithPayload: true,
	}
	jsonData, _ := json.Marshal(payload)

	url := fmt.Sprintf("%s/collections/audio_memory/points/search", QdrantURL)
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return "", nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", nil, fmt.Errorf("qdrant status: %d", resp.StatusCode)
	}

	var result QdrantSearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", nil, err
	}

	var contextBuffer bytes.Buffer
	var sources []string

	for _, hit := range result.Result {
		contextBuffer.WriteString(hit.Payload.Summary + "\n")
		sources = append(sources, fmt.Sprintf("%s (Score: %.2f)", hit.Payload.FilePath, hit.Score))
	}

	if contextBuffer.Len() == 0 {
		return "", nil, fmt.Errorf("hafızada eşleşen kayıt bulunamadı")
	}

	return contextBuffer.String(), sources, nil
}

func generateResponse(prompt string) (string, error) {
	payload := GenerateRequest{
		Model:  "llama3",
		Prompt: prompt,
		Stream: false,
	}
	jsonData, _ := json.Marshal(payload)

	resp, err := http.Post(OllamaURL+"/api/generate", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	var result GenerateResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}
	return result.Response, nil
}