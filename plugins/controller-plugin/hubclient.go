package main

// HubClient — identyczny wzorzec jak w timer-plugin / replay-plugin.
// Zarządza połączeniem WebSocket z hubem, auto-reconnect, send/receive.

import (
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type Message struct {
	From      string                 `json:"from"`
	To        string                 `json:"to"`
	Type      string                 `json:"type"`
	Payload   map[string]interface{} `json:"payload"`
	Timestamp string                 `json:"timestamp,omitempty"`
}

type HubClient struct {
	pluginID   string
	pluginName string
	hubURL     string
	conn       *websocket.Conn
	send       chan []byte
	receive    chan *Message
	reconnect  chan struct{}
	done       chan struct{}
	mu         sync.RWMutex
	connected  bool
}

func NewHubClient(pluginID, pluginName, hubURL string) *HubClient {
	return &HubClient{
		pluginID:   pluginID,
		pluginName: pluginName,
		hubURL:     hubURL,
		send:       make(chan []byte, 1024),
		receive:    make(chan *Message, 1024),
		reconnect:  make(chan struct{}, 1),
		done:       make(chan struct{}),
	}
}

func (hc *HubClient) Connect() error {
	dialer := websocket.Dialer{HandshakeTimeout: 10 * time.Second}
	conn, _, err := dialer.Dial(hc.hubURL, nil)
	if err != nil {
		return fmt.Errorf("failed to connect to Hub: %w", err)
	}
	hc.mu.Lock()
	hc.conn = conn
	hc.connected = true
	hc.mu.Unlock()

	log.Printf("✅ Connected to Hub: %s", hc.hubURL)
	go hc.readPump()
	go hc.writePump()

	hc.Send(&Message{
		From: hc.pluginID,
		To:   "hub",
		Type: "register",
		Payload: map[string]interface{}{
			"id":      hc.pluginID,
			"name":    hc.pluginName,
			"type":    "plugin",
			"version": "1.0.0",
		},
	})

	// Subscribe to classes so hub can deliver broadcast:class messages to us.
	// Also required for late-join: hub sends plugin_status to main-module only
	// for expected plugins; subscriptions ensure we receive any future broadcasts.
	time.Sleep(100 * time.Millisecond)
	hc.Send(&Message{
		From: hc.pluginID,
		To:   "hub",
		Type: "subscribe",
		Payload: map[string]interface{}{
			"class": []string{"controller"},
		},
	})

	return nil
}

func (hc *HubClient) Send(msg *Message) error {
	hc.mu.RLock()
	connected := hc.connected
	hc.mu.RUnlock()
	if !connected {
		log.Printf("⚠️  Send failed — not connected (type=%s to=%s)", msg.Type, msg.To)
		return fmt.Errorf("not connected")
	}
	msg.Timestamp = time.Now().Format(time.RFC3339)
	if msg.From == "" {
		msg.From = hc.pluginID
	}
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	select {
	case hc.send <- data:
		return nil
	case <-time.After(time.Second):
		return fmt.Errorf("send buffer full")
	}
}

func (hc *HubClient) Receive() <-chan *Message {
	return hc.receive
}

func (hc *HubClient) readPump() {
	defer func() {
		hc.mu.Lock()
		hc.connected = false
		if hc.conn != nil {
			hc.conn.Close()
		}
		hc.mu.Unlock()
		select {
		case hc.reconnect <- struct{}{}:
		default:
		}
	}()

	hc.mu.RLock()
	conn := hc.conn
	hc.mu.RUnlock()

	conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	conn.SetPongHandler(func(string) error {
		conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		select {
		case <-hc.done:
			return
		default:
		}
		_, data, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err,
				websocket.CloseGoingAway,
				websocket.CloseAbnormalClosure) {
				log.Printf("❌ WebSocket read error: %v", err)
			}
			return
		}
		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			log.Printf("⚠️  Failed to parse message: %v", err)
			continue
		}
		select {
		case hc.receive <- &msg:
		case <-time.After(time.Second):
			log.Printf("⚠️  Receive buffer full, dropping message type=%s", msg.Type)
		}
	}
}

func (hc *HubClient) writePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-hc.done:
			return
		case data, ok := <-hc.send:
			hc.mu.RLock()
			conn := hc.conn
			hc.mu.RUnlock()
			if !ok || conn == nil {
				return
			}
			conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
				log.Printf("❌ Write error: %v", err)
				return
			}
		case <-ticker.C:
			hc.mu.RLock()
			conn := hc.conn
			hc.mu.RUnlock()
			if conn == nil {
				return
			}
			conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

func (hc *HubClient) AutoReconnect() {
	backoff := time.Second
	for {
		select {
		case <-hc.done:
			return
		case <-hc.reconnect:
			log.Printf("🔄 Reconnecting to Hub...")
			time.Sleep(backoff)
			if err := hc.Connect(); err != nil {
				log.Printf("❌ Reconnect failed: %v", err)
				backoff *= 2
				if backoff > 30*time.Second {
					backoff = 30 * time.Second
				}
				select {
				case hc.reconnect <- struct{}{}:
				default:
				}
			} else {
				log.Printf("✅ Reconnected to Hub")
				backoff = time.Second
			}
		}
	}
}

func (hc *HubClient) Close() {
	close(hc.done)
	hc.mu.Lock()
	defer hc.mu.Unlock()
	if hc.conn != nil {
		hc.conn.WriteMessage(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
		)
		hc.conn.Close()
		hc.conn = nil
	}
	hc.connected = false
}
