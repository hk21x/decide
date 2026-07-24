/** Dark is the brand default; light is a first-class alternative, toggled
 * in Settings and persisted locally. Applied via data-theme on <html> —
 * every token utility follows because Tailwind v4 compiles them to var(). */

export type Theme = "dark" | "light";

const STORAGE_KEY = "decide-theme";
const THEME_COLOUR: Record<Theme, string> = {
  dark: "#151021",
  light: "#F7F5FA",
};

export function getTheme(): Theme {
  return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
}

export function setTheme(theme: Theme): void {
  localStorage.setItem(STORAGE_KEY, theme);
  apply(theme);
}

export function initTheme(): void {
  apply(getTheme());
}

function apply(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", THEME_COLOUR[theme]);
}
