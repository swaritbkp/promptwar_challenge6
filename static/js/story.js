/**
 * HawaKhata Story Mode Controller
 * Handles deterministic guided tours (?story=ncr|chd) with keyboard navigation.
 */

export class StoryController {
  constructor(app) {
    this.app = app;
    this.active = false;
    this.currentStep = 0;
    this.steps = [];
    this.banner = document.getElementById("story-tour");
    this.stepText = document.getElementById("story-step-text");
    this.captionText = document.getElementById("story-caption-text");
    this.prevBtn = document.getElementById("story-prev-btn");
    this.nextBtn = document.getElementById("story-next-btn");
    this.closeBtn = document.getElementById("story-close-btn");

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
      const resp = await fetch(`/api/v1/story/${storyId}`);
      if (!resp.ok) return;
      const json = await resp.json();
      if (!json.data || !json.data.steps) return;
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
    if (this.stepText) this.stepText.textContent = `Step ${this.currentStep + 1} of ${this.steps.length}`;
    if (this.captionText) this.captionText.textContent = s.caption_en || s.caption || "";
    if (s.screen && this.app?.switchTab) this.app.switchTab(s.screen);
    if (this.prevBtn) this.prevBtn.disabled = this.currentStep === 0;
    if (this.nextBtn) this.nextBtn.textContent = this.currentStep === this.steps.length - 1 ? "Finish" : "Next";
  }

  next() {
    if (this.currentStep < this.steps.length - 1) {
      this.currentStep++;
      this.render();
    } else {
      this.stop();
    }
  }

  prev() {
    if (this.currentStep > 0) {
      this.currentStep--;
      this.render();
    }
  }

  stop() {
    this.active = false;
    if (this.banner) this.banner.hidden = true;
  }
}
