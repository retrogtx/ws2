llm chat with centrifugo websockets

todo; make two llms talk with eachother

## Setup

1. Install dependencies:
```bash
cd frontend && bun install

cd backend && bun install
```

2. Configure environment variables:
```bash
# Backend
export ANTHROPIC_API_KEY="your-anthropic-key"
export PORT=8787
export CENTRIFUGO_HTTP_URL="http://localhost:8000"

# Frontend
export NEXT_PUBLIC_BACKEND_URL="http://localhost:8787"
export NEXT_PUBLIC_CENTRIFUGO_WS_URL="ws://localhost:8000/connection/websocket"
```
I made the project with just the anthropic key in backend/.env
there's port defined within the code as OR statements (for example: backendUrl: process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8787') so its fine if you don't define ports in the env 

3. Start Centrifugo:
```bash
centrifugo --config config.json
```

4. Start backend:
```bash
cd backend && bun run dev
```

5. Start frontend:
```bash
cd frontend && bun run dev
```

## Overall Flow

┌─────────────────┐    HTTP POST     ┌─────────────────┐    AI API Call    ┌─────────────────┐
│   Frontend      │ ──────────────► │    Backend      │ ─────────────────► │   Anthropic     │
│                 │                 │                 │                    │   Claude API    │
│ - React + AI SDK│ ◄────────────── │ - Express.js    │ ◄───────────────── │                 │
│ - useChat()     │  WebSocket      │ - streamText()  │   Streamed Text    │                 │
│ - Centrifugo    │  Stream         │ - Centrifugo    │                    │                 │
│   Transport     │                 │   Publishing    │                    │                 │
└─────────────────┘                 └─────────────────┘                    └─────────────────┘
         │                                    │
         │                                    │
         ▼                                    ▼
┌─────────────────┐                 ┌─────────────────┐
│   Centrifugo    │ ◄────────────── │   Centrifugo    │
│   WebSocket     │   Real-time     │   HTTP API      │
│   Server        │   Streaming     │   Publishing    │
└─────────────────┘                 └─────────────────┘

1. User sends message via HTTP POST to `/api/chat`
2. Backend generates channel and messageId, responds immediately
3. Backend streams AI response chunks via Centrifugo WebSocket
4. Frontend receives real-time updates through persistent WebSocket connection
5. AI SDK UI renders streaming text with "thinking" indicator

## Files

- `frontend/components/chat.tsx` - Main chat UI component
- `frontend/lib/centrifugo-transport.ts` - Custom WebSocket transport layer
- `backend/index.ts` - Express server with AI integration
- `config.json` - Centrifugo configuration
