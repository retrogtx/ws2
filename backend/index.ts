import express from "express";
import type { Request, Response } from "express";
import cors from "cors";
import { readFileSync } from "fs";
import path from "path";
import { createHmac } from "crypto";
import { streamText } from "ai";
import { createAnthropic } from "@ai-sdk/anthropic";

interface CentrifugoConfig {
  token_hmac_secret_key: string;
  api_key: string;
  allowed_origins: string[];
}

interface ChatRequestBody {
  messages: Array<{ role: string; content: string }>;
  model?: string;
  id?: string;
  data?: any;
}

const app = express();
const PORT = Number(process.env.PORT || 8787);

app.use(cors({
  origin: [
    'http://localhost:3000', 
    'http://localhost:5173',
    'https://ws2.fly.dev'
  ],  
  credentials: true
}));
app.use(express.json());

function readCentrifugoConfig(): CentrifugoConfig {
  const configPath = path.resolve("./config.json");
  const raw = readFileSync(configPath, "utf8");
  return JSON.parse(raw) as CentrifugoConfig;
}

function generateCentrifugoToken(userId: string = 'anonymous'): string {
  const config = readCentrifugoConfig();
  const header = { alg: "HS256", typ: "JWT" };
  const payload = { sub: userId };

  const encodedHeader = Buffer.from(JSON.stringify(header)).toString('base64url');
  const encodedPayload = Buffer.from(JSON.stringify(payload)).toString('base64url');

  const data = `${encodedHeader}.${encodedPayload}`;

  const hmac = createHmac('sha256', config.token_hmac_secret_key);
  hmac.update(data);
  const signature = hmac.digest('base64url');

  return `${data}.${signature}`;
}

async function centrifugoPublish(
  channel: string,
  data: unknown,
  centrifugoBaseUrl = process.env.CENTRIFUGO_HTTP_URL || "http://localhost:8000"
): Promise<void> {
  const config = readCentrifugoConfig();
  console.log('Publishing to Centrifugo:', { channel, data });
  const res = await fetch(`${centrifugoBaseUrl}/api/publish`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `apikey ${config.api_key}`,
      "X-API-Key": config.api_key,
    },
    body: JSON.stringify({
      channel,
      data,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    console.error('Centrifugo publish failed:', res.status, text);
    throw new Error(`Centrifugo publish failed: ${res.status} ${text}`);
  }
  console.log('Successfully published to Centrifugo');
}

app.post("/api/chat", async (req: Request<unknown, unknown, ChatRequestBody>, res: Response) => {
  try {
    const { messages, model, id } = req.body || {};
    console.log("Received messages:", JSON.stringify(messages, null, 2));
    if (!messages || !Array.isArray(messages)) {
      res.status(400).json({ error: "Missing 'messages' array" });
      return;
    }

    const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
    if (!ANTHROPIC_API_KEY) {
      throw new Error("ANTHROPIC_API_KEY is not set");
    }

    const channel = `chat:${id || 'default'}`;
    const messageId = Date.now().toString() + '_' + Math.random().toString(36).slice(2, 11);

    res.json({ channel, messageId });

    (async () => {
      try {
        const anthropic = createAnthropic({ apiKey: ANTHROPIC_API_KEY });
        const modelId = model && typeof model === "string" ? model : "claude-3-5-haiku-20241022";

        const result = await streamText({
          model: anthropic(modelId),
          messages: messages.map((msg: any) => {
            let content = "";
            if (msg.parts && Array.isArray(msg.parts)) {
              const textParts = msg.parts.filter((part: any) => part.type === "text" && part.text);
              content = textParts.map((part: any) => part.text).join("");
            } else if (msg.content) {
              content = msg.content;
            }
            
            if (!content.trim()) {
              content = "..."; 
            }
            
            return {
              role: msg.role as "user" | "assistant" | "system",
              content: content,
            };
          }),
        });

        console.log('Starting to stream to channel:', channel, 'messageId:', messageId);
        for await (const delta of result.textStream) {
          console.log('Publishing delta:', delta);
          await centrifugoPublish(channel, {
            type: "text",
            content: delta,
            done: false,
            messageId
          });
        }

        console.log('Stream completed, sending done signal');
        await centrifugoPublish(channel, {
          type: "text",
          content: "",
          done: true,
          messageId
        });
      } catch (error) {
        console.error("Streaming error:", error);
        try {
          await centrifugoPublish(channel, {
            type: "error",
            error: "Failed to generate response"
          });
        } catch (publishError) {
          console.error("Failed to publish error:", publishError);
        }
      }
    })();
  } catch (error) {
    console.error("Chat endpoint error:", error);
    if (!res.headersSent) {
      res.status(500).json({ error: "Internal error" });
    }
  }
});

app.get("/api/centrifugo-token", async (req: Request, res: Response) => {
  try {
    const userId = (req.query.userId as string) || 'anonymous';
    const token = generateCentrifugoToken(userId);
    res.json({
      success: true,
      token
    });
  } catch (error) {
    console.error("Token generation error:", error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate token'
    });
  }
});

app.listen(PORT, () => {
  console.log(`Backend listening on http://localhost:${PORT}`);
});