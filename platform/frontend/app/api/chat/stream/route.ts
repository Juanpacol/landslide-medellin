export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

// next.config.mjs usa rewrites() para /api/:path* -> backend, pero rewrites()
// bufferiza la respuesta completa antes de entregarla (rompe SSE). Este route
// handler de filesystem tiene prioridad sobre el rewrite genérico y retransmite
// el ReadableStream del backend sin bufferizar.
export async function POST(req: Request) {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
  const body = await req.text();

  const upstream = await fetch(`${backendUrl}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
