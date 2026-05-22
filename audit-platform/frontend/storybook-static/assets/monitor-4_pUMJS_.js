function t(n){n.duration>3e3&&console.warn(`[慢请求] ${n.method} ${n.url} ${n.duration}ms`)}export{t as logRequest};
