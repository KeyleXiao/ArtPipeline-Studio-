/** API 客户端 */
const API = {
  async json(path, options = {}) {
    const res = await fetch(path, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      let msg = res.statusText;
      let payload = null;
      try {
        const t = await res.text();
        if (t) {
          try {
            payload = JSON.parse(t);
            const d = payload?.detail;
            if (typeof d === "string") msg = d;
            else if (d && typeof d === "object" && !Array.isArray(d)) {
              msg = d.message || d.code || msg;
            } else if (Array.isArray(d)) {
              msg = d.map((x) => x.msg || x.message || JSON.stringify(x)).join("; ");
            }
          } catch {
            msg = t.slice(0, 300);
          }
        }
      } catch (_) {}
      const err = new Error(msg);
      const d = payload?.detail;
      if (d && typeof d === "object" && !Array.isArray(d)) {
        err.code = d.code;
        err.detail = d;
      }
      err.status = res.status;
      throw err;
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  },
  get: (p) => API.json(p),
  post: (p, body) =>
    API.json(p, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : "{}",
    }),
  put: (p, body) =>
    API.json(p, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  del: (p) => API.json(p, { method: "DELETE" }),
  postForm: (p, formData) =>
    API.json(p, {
      method: "POST",
      body: formData,
    }),
};

export { API };
