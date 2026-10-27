import homepage from "../knowledge/steadfst.html";

const HTML_HEADERS = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "public, max-age=300"
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/api/graph") {
      const base = "https://raw.githubusercontent.com/rllibo833-sudo/mnemos-RLI/Knowledge/knowledge/";
      const headers = { "accept": "application/json" };
      try {
        const manifestResponse = await fetch(base + "manifest.json", { headers });
        if (!manifestResponse.ok) throw new Error("Knowledge manifest unavailable (" + manifestResponse.status + ")");
        const manifest = await manifestResponse.json();
        const [nodeResults, edgeResults] = await Promise.all([
          Promise.all((manifest.node_files || []).map(async (name) => {
            const response = await fetch(base + "nodes/" + encodeURIComponent(name), { headers });
            if (!response.ok) throw new Error("Knowledge node unavailable: " + name);
            return response.json();
          })),
          Promise.all((manifest.edge_files || []).map(async (name) => {
            const response = await fetch(base + "edges/" + encodeURIComponent(name), { headers });
            if (!response.ok) throw new Error("Knowledge edges unavailable: " + name);
            return response.json();
          }))
        ]);
        const nodes = nodeResults.flat().filter(node => !node.deleted_at);
        const edges = edgeResults.flat().filter(edge => !edge.deleted_at).map(edge => ({
          ...edge,
          source_node_id: edge.source_node_id ?? edge.source_id ?? edge.source,
          target_node_id: edge.target_node_id ?? edge.target_id ?? edge.target,
          relation_type: edge.relation_type ?? edge.relation
        }));
        return Response.json({
          manifest,
          nodes,
          edges,
          source: "mnemos-RLI:Knowledge",
          generated_at: manifest.generated_at
        }, {
          headers: {
            "cache-control": "public, max-age=30, stale-while-revalidate=120",
            "access-control-allow-origin": "*"
          }
        });
      } catch (error) {
        return Response.json({ error: "Knowledge graph could not be loaded", detail: String(error?.message || error) }, {
          status: 502,
          headers: { "cache-control": "no-store", "access-control-allow-origin": "*" }
        });
      }
    }

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
