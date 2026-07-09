import { NextResponse } from 'next/server';
import { environment } from '@/config/environment';
import { normalizeHost, shouldUseSameOriginApiBase } from './route-utils';

const LOCALHOST_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

const normalizeHostname = (host: string) => {
  const trimmed = host.trim().toLowerCase();
  if (!trimmed) {
    return '';
  }
  if (trimmed.startsWith('[')) {
    const closingBracket = trimmed.indexOf(']');
    return closingBracket >= 0 ? trimmed.slice(0, closingBracket + 1) : trimmed;
  }
  return trimmed.split(':')[0] || '';
};

const isLocalDevHost = (host: string) => {
  return LOCALHOST_HOSTS.has(normalizeHostname(host));
};

const isLocaltestHost = (host: string) => {
  return normalizeHostname(host).endsWith('.localtest.me');
};

export async function GET(request: Request) {
  const configured = environment.apiBaseUrl || '';

  // On a custom (white-label) domain the request host differs from the
  // configured API origin. Returning the absolute main-domain URL would make
  // the browser issue cross-origin API calls that are blocked by CORS, so
  // return an empty base and let the client use same-origin relative requests
  // (the custom-domain ingress already routes /api to the backend). The main
  // domain keeps its configured absolute base unchanged.
  if (configured) {
    try {
      const configuredHost = new URL(configured).host.toLowerCase();
      const requestHost = normalizeHost(
        request.headers.get('x-forwarded-host') ||
          request.headers.get('host') ||
          '',
      );
      // Local frontend dev commonly runs on :3000 while the API runs on :8080.
      // If the dev API is configured as api.localtest.me, keep localhost/127.0.0.1
      // browsers on same-origin /api so users are not blocked by local DNS/proxy
      // behavior around localtest.me.
      if (isLocalDevHost(requestHost) && isLocaltestHost(configuredHost)) {
        return NextResponse.json({ apiBaseUrl: '' });
      }
      // Localhost-to-localhost still crosses ports in the browser. Keep local
      // development on same-origin /api so Next dev rewrites handle the backend
      // hop without CORS.
      if (isLocalDevHost(requestHost) && isLocalDevHost(configuredHost)) {
        return NextResponse.json({ apiBaseUrl: '' });
      }
      if (shouldUseSameOriginApiBase(configuredHost, requestHost)) {
        return NextResponse.json({ apiBaseUrl: '' });
      }
    } catch {
      // Fall back to the configured value if the URL cannot be parsed.
    }
  }

  return NextResponse.json({ apiBaseUrl: configured });
}
