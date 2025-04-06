// Handle CORS for local development
browser.webRequest.onBeforeSendHeaders.addListener(
    function(details) {
        let headers = details.requestHeaders;
        headers.push({
            name: "Access-Control-Allow-Origin",
            value: "*"
        });
        headers.push({
            name: "Access-Control-Allow-Methods",
            value: "GET, POST, PUT, DELETE, OPTIONS"
        });
        headers.push({
            name: "Access-Control-Allow-Headers",
            value: "Content-Type, X-API-Key"
        });
        return { requestHeaders: headers };
    },
    { urls: ["http://localhost:5000/*"] },
    ["blocking", "requestHeaders", "extraHeaders"]
); 