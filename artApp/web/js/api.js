/** API 客户端 */
const API = {
  async json(path, options = {}) {
    const res = await fetch(path, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const t = await res.text();
        if (t) {
          try {
            const j = JSON.parse(t);
            if (typeof j.detail === "string") msg = j.detail;
            else if (Array.isArray(j.detail))
              msg = j.detail.map((d) => d.msg || d.message || JSON.stringify(d)).join("; ");
          } catch {
            msg = t.slice(0, 300);
          }
        }
      } catch (_) {}
      throw new Error(msg);
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
