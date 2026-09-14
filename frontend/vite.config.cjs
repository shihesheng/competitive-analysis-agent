const { defineConfig } = require("vite");
const react = require("@vitejs/plugin-react");

function forceViteClientMimeType() {
  return {
    name: "force-vite-client-mime-type",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = req.url?.split("?")[0];

        if (path === "/@vite/client" || path === "/@react-refresh") {
          const setHeader = res.setHeader.bind(res);

          res.setHeader = (name, value) => {
            if (String(name).toLowerCase() === "content-type") {
              return setHeader(name, "text/javascript");
            }

            return setHeader(name, value);
          };
        }

        next();
      });
    },
  };
}

module.exports = defineConfig({
  plugins: [forceViteClientMimeType(), react()],
});
