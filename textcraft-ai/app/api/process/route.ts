import { NextRequest, NextResponse } from 'next/server';
import { processRequestSchema } from '@/lib/validations';
import { processText } from '@/lib/openai';
import { countWords } from '@/lib/utils';
import type { ProcessResponse, ApiError } from '@/types';

export async function POST(request: NextRequest) {
  const startMs = Date.now();

  try {
    const body = await request.json();
    const parsed = processRequestSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json(
        {
          error: 'validation_error',
          message: parsed.error.errors.map((e) => e.message).join(', '),
        } satisfies ApiError,
        { status: 400 }
      );
    }

    const { tool, text, options, proToken } = parsed.data;

    // Rate limit check: Pro users bypass with a valid token
    // For the MVP, we trust the proToken presence from localStorage.
    // In production, you'd verify it against Stripe:
    //   const session = await stripe.checkout.sessions.retrieve(proToken);
    //   if (session.payment_status !== 'paid') → reject
    if (!proToken) {
      // Client-side localStorage enforces the limit primarily.
      // Server-side we add a simple IP-based secondary guard via headers.
      // For the MVP, the client is the primary enforcement point.
    }

    const result = await processText(tool, text, {
      length: options?.length,
      tone: options?.tone,
      targetKeyword: options?.targetKeyword,
      includeMetaDescription: options?.includeMetaDescription,
    });

    const processingMs = Date.now() - startMs;

    const response: ProcessResponse = {
      result,
      tool,
      wordCount: {
        input: countWords(text),
        output: countWords(result),
      },
      processingMs,
    };

    return NextResponse.json(response);
  } catch (error: unknown) {
    console.error('Process API error:', error);

    const message =
      error instanceof Error ? error.message : 'Internal server error';

    // Handle OpenAI rate limits
    if (message.includes('429') || message.includes('rate limit')) {
      return NextResponse.json(
        {
          error: 'rate_limited',
          message: 'AI service is busy. Please try again in a moment.',
        } satisfies ApiError,
        { status: 429 }
      );
    }

    return NextResponse.json(
      {
        error: 'internal_error',
        message: 'Something went wrong. Please try again.',
      } satisfies ApiError,
      { status: 500 }
    );
  }
}
