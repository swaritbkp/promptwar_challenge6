// Native ES Module: RFC 5545 iCalendar (.ics) routine window export

/**
 * Exports a clean-air schedule block or multi-day slot to an RFC 5545 .ics file.
 *
 * @param {Object} slot - Scheduled slot information.
 * @param {HTMLElement|null} btn - Optional button element to give visual confirmation.
 * @param {string} locationName - City / locality string for the event location.
 * @param {boolean} isHi - Whether the current language is Hindi.
 */
export function exportSlotIcs(slot, btn = null, locationName = "Delhi NCR", isHi = false) {
  if (!slot) return;
  const pad = (n) => String(n).padStart(2, "0");
  const toUtc = (dt) =>
    `${dt.getUTCFullYear()}${pad(dt.getUTCMonth() + 1)}${pad(dt.getUTCDate())}T${pad(dt.getUTCHours())}${pad(dt.getUTCMinutes())}00Z`;

  const start = new Date(Date.now() + (slot.day_index || 1) * 86400000);
  start.setHours(slot.start_hour || 13, 0, 0, 0);
  const end = new Date(start.getTime() + Math.max(1, (slot.end_hour - slot.start_hour) || 1) * 3600000);

  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//HawaKhata//Air Passbook//EN",
    "BEGIN:VEVENT",
    `UID:hk-${Date.now()}@hawakhata.org`,
    `DTSTAMP:${toUtc(new Date())}`,
    `DTSTART:${toUtc(start)}`,
    `DTEND:${toUtc(end)}`,
    `SUMMARY:HawaKhata Clean Window: ${slot.day_label || "Clean Window"} ${slot.time_label || ""}`,
    `DESCRIPTION:Scheduled clean air window in ${locationName}. Dilutes PM2.5 to ${slot.outdoor_pm25 || 95} ug/m3; saves ${slot.savings_ug || 210} ug.`,
    `LOCATION:${locationName}`,
    "STATUS:CONFIRMED",
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");

  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `hawakhata-${(slot.day_label || "routine").toLowerCase().replace(/\s+/g, "-")}-routine.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  if (btn) {
    const orig = btn.textContent;
    btn.textContent = isHi ? "✓ सहेज लिया गया" : "✓ Saved .ics";
    setTimeout(() => {
      btn.textContent = orig;
    }, 2000);
  }
}
