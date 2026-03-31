import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export default openai;

export const PROMPTS = {
  summarize: (text: string, length: string = 'medium') => ({
    system: `You are a professional text summarizer. Create a ${length} summary. Keep only the most important points. Use clear, concise language. Return ONLY the summary, no preamble or labels.`,
    user: text,
  }),

  rewrite: (text: string, tone: string = 'formal') => ({
    system: `You are a professional text rewriter. Rewrite the given text in a ${tone} tone. Maintain the original meaning but adjust the style and vocabulary. Return ONLY the rewritten text, no preamble or labels.`,
    user: text,
  }),

  seo: (text: string, keyword?: string, includeMeta: boolean = true) => ({
    system: `You are an SEO content specialist. Optimize the given text for search engines${keyword ? ` targeting the keyword: "${keyword}"` : ''}.
- Improve readability and keyword density naturally
- Add relevant semantic keywords
- Structure with clear sentences
${includeMeta ? '- Add a meta description at the end on a new line, prefixed with "META: "' : ''}
Return ONLY the optimized text${includeMeta ? ' (plus META line)' : ''}, no preamble.`,
    user: text,
  }),
};

export async function processText(
  tool: 'summarize' | 'rewrite' | 'seo',
  text: string,
  options: {
    length?: string;
    tone?: string;
    targetKeyword?: string;
    includeMetaDescription?: boolean;
  } = {}
): Promise<string> {
  let prompt: { system: string; user: string };

  switch (tool) {
    case 'summarize':
      prompt = PROMPTS.summarize(text, options.length || 'medium');
      break;
    case 'rewrite':
      prompt = PROMPTS.rewrite(text, options.tone || 'formal');
      break;
    case 'seo':
      prompt = PROMPTS.seo(text, options.targetKeyword, options.includeMetaDescription ?? true);
      break;
  }

  const completion = await openai.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: prompt.system },
      { role: 'user', content: prompt.user },
    ],
    temperature: 0.7,
    max_tokens: 2000,
  });

  return completion.choices[0]?.message?.content?.trim() || '';
}
