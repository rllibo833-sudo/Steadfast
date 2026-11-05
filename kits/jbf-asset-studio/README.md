# JBF Asset Studio

Free first image-generation SaaS beta for indie game creators. It runs as an isolated Cloudflare Worker with a static browser UI and Cloudflare Workers AI's hosted `@cf/bytedance/stable-diffusion-xl-lightning` model. No image or prompt is stored by this application; the durable object keeps only daily hashed visitor counts and a shared generation cap.

The first release offers game-art, pixel-art, character, world, and product-illustration styles, PNG download, two images per visitor per day, and a global 160-image daily cap. Video generation is not included. No paid model fallback is configured.

The model is marked Beta and its hosted pricing is currently listed as $0 per step by Cloudflare. Availability, pricing, and model terms can change; the app therefore remains capped and labels the output as beta. Visitors should review the model license before commercial use.

The public site displays the owner-approved business email and WhatsApp contact. Values are stored as Cloudflare Worker secrets, not committed to this repository.

Deploy with `wrangler deploy --config kits/jbf-asset-studio/wrangler.toml --name jbf-asset-studio`.
