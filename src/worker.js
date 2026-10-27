import homepage from "../knowledge/steadfst.html";

const HTML_HEADERS = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "public, max-age=300"
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({ service: "steadfast-agent-cloud", status: "ok" });
    }

    if (url.pathname === "/sitemap.xml") {
      return new Response('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url>\n    <loc>https://steadfast-agent-cloud.fadlibo833.workers.dev/steadfst.html</loc>\n  </url>\n</urlset>\n', {
        headers: { "content-type": "application/xml; charset=utf-8", "cache-control": "public, max-age=300" }
      });
    }

    if (url.pathname === "/robots.txt") {
      return new Response('User-agent: *\nAllow: /\n\nSitemap: https://steadfast-agent-cloud.fadlibo833.workers.dev/sitemap.xml\n', {
        headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "public, max-age=300" }
      });
    }

    if (url.pathname === "/" || url.pathname === "/steadfst.html") {
      return new Response(homepage, { headers: HTML_HEADERS });
    }

    return new Response("Not found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" }
    });
  }
};
