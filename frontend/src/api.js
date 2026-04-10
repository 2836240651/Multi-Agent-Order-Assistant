const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export const api = {
  health() {
    return request("/health");
  },
  chat(payload) {
    return request("/api/chat", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  user(userId) {
    return request(`/api/users/${encodeURIComponent(userId)}`);
  },
  chatHistory(userId, orderId) {
    const query = new URLSearchParams({ user_id: userId, order_id: orderId });
    return request(`/api/chat/history?${query.toString()}`);
  },
  ticketStateMachine() {
    return request("/api/tickets/state-machine");
  },
  tickets(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, String(value));
      }
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request(`/api/tickets${suffix}`);
  },
  ticket(ticketId, userId) {
    const query = new URLSearchParams();
    if (userId) {
      query.set("user_id", userId);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request(`/api/tickets/${encodeURIComponent(ticketId)}${suffix}`);
  },
  transitionTicket(ticketId, payload, userId) {
    const query = new URLSearchParams();
    if (userId) {
      query.set("user_id", userId);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request(`/api/tickets/${encodeURIComponent(ticketId)}/transition${suffix}`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  pendingReviews() {
    return request("/api/reviews/pending");
  },
  approveReview(reviewId, reviewerNote) {
    return request(`/api/reviews/${reviewId}/approve`, {
      method: "POST",
      body: JSON.stringify({ reviewer_note: reviewerNote })
    });
  },
  rejectReview(reviewId, reviewerNote) {
    return request(`/api/reviews/${reviewId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewer_note: reviewerNote })
    });
  },
  auditLogs() {
    return request("/api/audit/logs");
  },
  metrics() {
    return request("/api/metrics");
  },
  opsOverview() {
    return request("/api/ops/overview");
  },
  rollout() {
    return request("/api/ops/rollout");
  },
  updateRollout(weights) {
    return request("/api/ops/rollout", {
      method: "POST",
      body: JSON.stringify(weights)
    });
  },
  resetDemo() {
    return request("/api/demo/reset", {
      method: "POST"
    });
  },
  runCase(caseName, rolloutVariant) {
    const query = new URLSearchParams({ case: caseName });
    if (rolloutVariant) {
      query.set("rollout_variant", rolloutVariant);
    }
    return request(`/api/demo/run_case?${query.toString()}`);
  }
};
