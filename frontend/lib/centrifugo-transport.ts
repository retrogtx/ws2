import { Centrifuge, PublicationContext, Subscription } from 'centrifuge';
import { ChatTransport, UIMessage, UIMessageChunk, UIDataTypes, UITools, ChatRequestOptions } from 'ai';

export class CentrifugoChatTransport implements ChatTransport<UIMessage<UIDataTypes, UITools>> {
  private centrifuge: Centrifuge | null = null;
  private subscriptions = new Map<string, Subscription>();
  private listeners = new Map<string, Set<(ctx: PublicationContext) => void>>();

  constructor(
    private config: {
      centrifugoUrl: string;
      backendUrl: string;
      getToken: () => Promise<string>;
    }
  ) {}

  async prepare() {
    if (this.centrifuge) return;

    try {
      const token = await this.config.getToken();
      this.centrifuge = new Centrifuge(this.config.centrifugoUrl, { token });
      
      this.centrifuge.connect();
    } catch (error) {
      console.error('Failed to prepare Centrifugo:', error);
      throw error;
    }
  }

  async sendMessages(options: {
    trigger: 'submit-message' | 'regenerate-message';
    chatId: string;
    messageId: string | undefined;
    messages: UIMessage<UIDataTypes, UITools>[];
    abortSignal: AbortSignal | undefined;
  } & ChatRequestOptions): Promise<ReadableStream<UIMessageChunk<UIDataTypes, UITools>>> {
    await this.prepare();

    if (!this.centrifuge) {
      throw new Error('Centrifugo not initialized');
    }

    const response = await fetch(`${this.config.backendUrl}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: options.chatId,
        messages: options.messages,
      }),
      signal: options.abortSignal,
    });

    if (!response.ok) {
      throw new Error(`Backend error: ${response.status}`);
    }

    const { channel, messageId } = await response.json();

    if (!this.subscriptions.has(options.chatId)) {
      console.log(`Creating persistent subscription for chatId: ${options.chatId}, channel: ${channel}`);
      const sub = this.centrifuge!.newSubscription(channel);
      sub.subscribe();
      this.subscriptions.set(options.chatId, sub);
    }

    return this.createMessageStream(options.chatId, messageId, options.abortSignal);
  }

  private createMessageStream(chatId: string, targetMessageId: string, abortSignal?: AbortSignal): ReadableStream<UIMessageChunk<UIDataTypes, UITools>> {
    let isClosed = false;
    const sub = this.subscriptions.get(chatId)!;
    let listener: (ctx: PublicationContext) => void;

    return new ReadableStream({
      start: (controller) => {
        console.log(`Creating message stream for chatId: ${chatId}, messageId: ${targetMessageId}`);
        
        controller.enqueue({
          type: 'text-start',
          id: targetMessageId,
        });

        listener = (ctx: PublicationContext) => {
          const data = ctx.data;
          if (data.messageId !== targetMessageId) return; 
          
          console.log(`Received data for messageId: ${targetMessageId}`, data);
          
          if (data.type === 'text') {
            if (data.done) {
              console.log(`Message completed for messageId: ${targetMessageId}`);
              controller.enqueue({
                type: 'text-end',
                id: targetMessageId,
              });
              isClosed = true;
              controller.close();
            } else {
              controller.enqueue({
                type: 'text-delta',
                delta: data.content,
                id: targetMessageId,
              });
            }
          } else if (data.type === 'error') {
            console.log(`Error received for messageId: ${targetMessageId}`);
            isClosed = true;
            controller.error(new Error(data.error));
          }
        };

        sub.on('publication', listener);
        if (!this.listeners.has(chatId)) this.listeners.set(chatId, new Set());
        this.listeners.get(chatId)!.add(listener);

        abortSignal?.addEventListener('abort', () => {
          if (!isClosed) {
            console.log(`Abort signal received for messageId: ${targetMessageId}`);
            isClosed = true;
            this.listeners.get(chatId)!.delete(listener);
            controller.close();
          }
        });
      },
      cancel: () => {
        if (!isClosed) {
          console.log(`Stream cancelled for messageId: ${targetMessageId}`);
          isClosed = true;
          this.listeners.get(chatId)!.delete(listener);
        }
      },
    });
  }

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk<UIDataTypes, UITools>> | null> {
    return null;
  }

  async close() {
    if (this.centrifuge) {
      this.centrifuge.disconnect();
      this.centrifuge = null;
      this.subscriptions.clear();
      this.listeners.clear();
    }
  }
}
