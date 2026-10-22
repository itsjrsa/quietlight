// Apply before the stylesheet loads to avoid a light flash on dark-mode visits.
(() => {
  const key = "quietlight.theme.v1";
  const modes = ["system", "light", "dark"];
  const system = matchMedia("(prefers-color-scheme: dark)");
  let preference = "system";
  try {
    const saved = localStorage.getItem(key);
    if (modes.includes(saved)) preference = saved;
  } catch {
    // The theme still works for this visit when storage is unavailable.
  }
  function apply() {
    const dark =
      preference === "dark" || (preference === "system" && system.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.querySelector('meta[name="theme-color"]').content = dark
      ? "#191c19"
      : "#f9f9f6";
    document.querySelectorAll(".theme-toggle").forEach((button) => {
      const next = modes[(modes.indexOf(preference) + 1) % modes.length];
      const label = `Theme: ${preference}. Switch to ${next} mode`;
      button.setAttribute("aria-label", label);
      button.title = label;
      button.textContent = { system: "◐", light: "☼", dark: "☾" }[preference];
    });
  }
  apply();
  system.addEventListener("change", apply);
  window.addEventListener("storage", (event) => {
    if (event.key === key || event.key === null) {
      preference = modes.includes(event.newValue) ? event.newValue : "system";
      apply();
    }
  });
  document.addEventListener("quietlight:page", apply);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".theme-toggle")) return;
    preference = modes[(modes.indexOf(preference) + 1) % modes.length];
    try {
      localStorage.setItem(key, preference);
    } catch {}
    apply();
  });
})();
