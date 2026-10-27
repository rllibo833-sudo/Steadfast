export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({ service: "steadfast-agent-cloud", status: "ok" });
    }
    if (url.pathname === "/sitemap.xml") {
      url.pathname = "/seo/sitemap.xml";
      return env.ASSETS.fetch(new Request(url, request));
    }
    if (url.pathname === "/robots.txt") {
      url.pathname = "/seo/robots.txt";
      return env.ASSETS.fetch(new Request(url, request));
    }
    if (url.pathname === "/") {
      url.pathname = "/steadfst.html";
      return env.ASSETS.fetch(new Request(url, request));
    }
    return env.ASSETS.fetch(request);
  }
};
