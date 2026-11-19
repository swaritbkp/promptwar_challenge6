const $ = (id) => document.getElementById(id);

export class StoryController {
  constructor(app) {
    this.app = app;
    this.active = false;
    this.currentStep = 0;
    this.steps = [];
    this.banner = $("story-tour");
    this.stepText = $("story-step-text");
    this.captionText = $("story-caption-text");
    this.prevBtn = $("story-prev-btn");
    this.nextBtn = $("story-next-btn");
    this.closeBtn = $("story-close-btn");

    if (this.prevBtn) this.prevBtn.addEventListener("click", () => this.prev());
    if (this.nextBtn) this.nextBtn.addEventListener("click", () => this.next());
    if (this.closeBtn) this.closeBtn.addEventListener("click", () => this.stop());

    window.addEventListener("keydown", (e) => {
      if (!this.active) return;
      if (e.key === "ArrowRight") this.next();
      if (e.key === "ArrowLeft") this.prev();
      if (e.key === "Escape") this.stop();
    });
  }

  async start(storyId = "ncr") {
    try {
      if (storyId === "chd" && this.app?.applyLocation) {
        this.app.applyLocation("Chandigarh / Mohali", 30.7333, 76.7794);
      } else if (this.app?.applyLocation && storyId === "ncr") {
        this.app.applyLocation("Delhi NCR / Gurugram", 28.4595, 77.0266);
      }
      const resp = await fetch(`/api/v1/story/${storyId}`);
      if (!resp.ok) return;
      const json = await resp.json();
      if (!json.data?.steps) return;
      this.steps = json.data.steps;
      this.currentStep = 0;
      this.active = true;
      if (this.banner) this.banner.hidden = false;
      this.render();
    } catch {}
  }

  render() {
    if (!this.active || !this.steps.length) return;
    const s = this.steps[this.currentStep];
    const isHi = this.app?.currentLang === "hi";
    if (this.stepText) this.stepText.textContent = isHi ? `चरण ${this.currentStep + 1} / ${this.steps.length}` : `Step ${this.currentStep + 1} of ${this.steps.length}`;
    if (this.captionText) this.captionText.textContent = (isHi ? s.caption_hi : s.caption_en) || s.caption_en || s.caption || "";

    if (s.screen && ["today", "plan", "indoor", "swaps"].includes(s.screen) && this.app?.switchTab) {
      this.app.switchTab(s.screen);
    }
    const mWhy = $("modal-why");
    if (mWhy) mWhy.hidden = s.action !== "open_why";
    const dAsk = $("ask-drawer");
    if (dAsk) dAsk.hidden = s.id === "s6_ask" || s.action === "open_ask" ? false : true;

    if (s.action === "apply_plan") {
      const runBtn = $("btn-run-plan");
      if (runBtn) runBtn.click();
    }
    if (s.action === "set_mohalla") {
      const rng = $("mohalla-range");
      if (rng) {
        rng.value = 200;
        rng.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    if (s.target) {
      const targetEl = document.querySelector(s.target);
      if (targetEl) targetEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    if (this.prevBtn) this.prevBtn.disabled = this.currentStep === 0;
    if (this.nextBtn) this.nextBtn.textContent = this.currentStep === this.steps.length - 1 ? (isHi ? "समाप्त" : "Finish") : (isHi ? "आगे" : "Next");
  }

  next() {
    // If modal-why is open, close it first (keeps tour card above backdrop)
    const mWhy = $("modal-why");
    if (mWhy && !mWhy.hidden) { mWhy.hidden = true; }
    if (this.currentStep < this.steps.length - 1) {
      this.currentStep++;
      this.render();
    } else {
      this.stop();
    }
  }

  prev() {
    const mWhy = $("modal-why");
    if (mWhy && !mWhy.hidden) { mWhy.hidden = true; }
    if (this.currentStep > 0) {
      this.currentStep--;
      this.render();
    }
  }

  stop() {
    this.active = false;
    if (this.banner) this.banner.hidden = true;
    const mWhy = $("modal-why");
    if (mWhy) mWhy.hidden = true;
    const dAsk = $("ask-drawer");
    if (dAsk) dAsk.hidden = true;
  }
}
