// Native ES Module: Unified API client for HawaKhata backend services

async function request(url, options = {}) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    const err = new Error(errorData?.error?.message || `HTTP ${resp.status}`);
    err.status = resp.status;
    err.data = errorData;
    throw err;
  }
  return resp.json();
}

export const api = {
  async fetchMeta() {
    const json = await request("/api/v1/meta");
    return json.data || {};
  },

  async fetchFourDayForecast({ lat = 28.4595, lng = 77.0266, city = "Delhi NCR", activity = "walk", durationMin = 60, ageBand = "31_41" } = {}) {
    const q = new URLSearchParams({
      lat: String(lat),
      lng: String(lng),
      city: String(city),
      activity: String(activity),
      duration_min: String(durationMin),
      age_band: String(ageBand),
    });
    const json = await request(`/api/v1/forecast/4day?${q.toString()}`);
    return json.data || {};
  },

  async postPassbook(profile) {
    const json = await request("/api/v1/passbook", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    });
    return json.data || {};
  },

  async postPlan({ profile, memberId, flexibleActivities }) {
    const json = await request("/api/v1/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile,
        member_id: memberId,
        flexible_activities: flexibleActivities,
      }),
    });
    return json.data || {};
  },

  async postIndoorSimulate({ room, sources = [], location }) {
    const json = await request("/api/v1/indoor/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room, sources, location }),
    });
    return json.data || {};
  },

  async postPetGuidance({ species = "dog", location }) {
    const json = await request("/api/v1/pet-guidance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ species, location }),
    });
    return json.data || {};
  },

  async postSwapsImpact({ swapId, unitsPerDay, daysPerWeek = 5, households = 1, participationRate = 1.0, location = null }) {
    const body = {
      swap_id: swapId,
      units_per_day: unitsPerDay,
      days_per_week: daysPerWeek,
      households,
      participation_rate: participationRate,
    };
    if (location) body.location = location;
    const json = await request("/api/v1/swaps/impact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return json.data || {};
  },

  async postChat({ message, sessionId = null, language = "en", profile = null }) {
    const body = { message, language };
    if (sessionId) body.session_id = sessionId;
    if (profile) body.profile = profile;
    const json = await request("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return json.data || {};
  },

  async fetchI18n(lang = "en") {
    return request(`/static/i18n/${lang}.json`);
  },

  async fetchStory(storyId = "ncr") {
    const json = await request(`/api/v1/story/${storyId}`);
    return json.data || {};
  },
};
