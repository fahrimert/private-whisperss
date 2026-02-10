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
	"github.com/gofiber/fiber/v2/middleware/cors"
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

// Qdrant Search Request
type QdrantSearchRequest struct {
	Vector      []float64              `json:"vector,omitempty"`
	Filter      map[string]interface{} `json:"filter,omitempty"`
	Limit       int                    `json:"limit"`
	WithPayload bool                   `json:"with_payload"`
}

// Qdrant Payload
type QdrantPayload struct {
	Summary       string                 `json:"summary"`
	FilePath      string                 `json:"file_path"`
	Text          string                 `json:"text"`
	StressScore   float64                `json:"stress_score"`
	StressDetails map[string]interface{} `json:"stress_details"`
}

// --- MEVCUT: Search işlemi için cevap yapısı ---
type QdrantResponse struct {
	Result []struct {
		Score   float64       `json:"score"`
		Payload QdrantPayload `json:"payload"`
	} `json:"result"`
}

// --- Scroll işlemi için özel cevap yapısı ---
type QdrantScrollResponse struct {
	Result struct {
		Points []struct {
			Payload QdrantPayload `json:"payload"`
		} `json:"points"`
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

type StatusResponse struct {
	Status        string                 `json:"status"`
	StressScore   float64                `json:"stress_score"`
	StressDetails map[string]interface{} `json:"stress_details"`
	Transcript    string                 `json:"transcript"`
}

func main() {
	// 1. LOG AYARLARI (HATAYI GÖRMEK İÇİN)
	log.SetFlags(log.LstdFlags | log.Lshortfile)

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
			log.Println("✅ RabbitMQ'ya bağlanıldı!")
			break
		}
		log.Printf("⏳ RabbitMQ bekleniyor (%d/10)...\n", i+1)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		log.Fatal("RabbitMQ bağlantı hatası:", err)
	}
	defer conn.Close()

	ch, _ := conn.Channel()
	defer ch.Close()

	q, _ := ch.QueueDeclare("task_queue", true, false, false, false, nil)

	app := fiber.New()

	app.Use(cors.New(cors.Config{
		AllowOrigins: "*",
		AllowHeaders: "Origin, Content-Type, Accept",
	}))

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

		err = ch.Publish("", q.Name, false, false, amqp.Publishing{
			ContentType: "application/json",
			Body:        body,
		})

		if err != nil {
			return c.Status(500).SendString("Kuyruğa atılamadı")
		}

		log.Printf("📨 UPLOAD: Görev Kuyruğa Atıldı. ID: %s\n", id)
		
		return c.JSON(fiber.Map{
			"status":  "processing_started",
			"file_id": id,
			"job_id":  id,
			"message": "Dosya işlenmek üzere sıraya alındı.",
		})
	})

	// --- STATUS ENDPOINT (LOGLU) ---
	app.Get("/status/:id", func(c *fiber.Ctx) error {
		jobID := c.Params("id")
		
		// Log: İstek geldi mi?
		log.Printf("🔍 STATUS SORGUSU: %s aranıyor...\n", jobID)

		searchPayload := QdrantSearchRequest{
			Filter: map[string]interface{}{
				"must": []map[string]interface{}{
					{
						"key": "job_id",
						"match": map[string]interface{}{
							"value": jobID,
						},
					},
				},
			},
			Limit:       1,
			WithPayload: true,
		}

		jsonData, _ := json.Marshal(searchPayload)
		resp, err := http.Post(QdrantURL+"/collections/audio_memory/points/scroll", "application/json", bytes.NewBuffer(jsonData))
		
		if err != nil {
			log.Printf("⚠️ Qdrant Bağlantı Hatası: %v\n", err)
			return c.JSON(fiber.Map{"status": "pending"})
		}
		defer resp.Body.Close()

		if resp.StatusCode != 200 {
			log.Printf("⚠️ Qdrant Status Code: %d\n", resp.StatusCode)
			return c.JSON(fiber.Map{"status": "pending"})
		}

		// Scroll için doğru struct'ı kullanıyoruz
		var result QdrantScrollResponse 
		if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
			log.Printf("⚠️ JSON Decode Hatası: %v\n", err)
			return c.JSON(fiber.Map{"status": "pending"})
		}

		// Sonuç var mı kontrolü
		pointCount := len(result.Result.Points)
		if pointCount == 0 {
			log.Printf("⏳ Henüz sonuç yok (Worker çalışıyor)... ID: %s\n", jobID)
			return c.JSON(fiber.Map{"status": "pending"})
		}

		// KAYIT BULUNDU!
		payload := result.Result.Points[0].Payload
		log.Printf("✅ SONUÇ BULUNDU! Skor: %.2f - ID: %s\n", payload.StressScore, jobID)
		
		return c.JSON(StatusResponse{
			Status:        "completed",
			StressScore:   payload.StressScore,
			StressDetails: payload.StressDetails,
			Transcript:    payload.Text,
		})
	})

	app.Post("/chat", func(c *fiber.Ctx) error {
		var req ChatRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "Geçersiz istek gövdesi"})
		}

		log.Printf("🔎 Chat Sorusu: %s\n", req.Question)

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

	log.Println("🚀 Backend 8080 portunda başlatılıyor...")
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

	// Search işlemi için eski struct (QdrantResponse) doğru çalışıyor
	var result QdrantResponse
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