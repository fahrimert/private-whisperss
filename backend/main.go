package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/streadway/amqp"
)

type Job struct {
	ID       string `json:"job_id"`
	FilePath string `json:"file_path"`
	Status   string `json:"status"`
}

func main() {
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

	log.Fatal(app.Listen(":8080"))
}