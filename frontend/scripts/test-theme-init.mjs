import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const script = await readFile(new URL("../public/theme-init.js", import.meta.url), "utf8");

function resolveTheme(stored, systemDark) {
  let applied;
  vm.runInNewContext(script, {
    localStorage: { getItem: () => stored },
    window: { matchMedia: () => ({ matches: systemDark }) },
    document: { documentElement: { classList: { toggle: (name, value) => {
      assert.equal(name, "dark");
      applied = value;
    } } } },
  });
  return applied;
}

assert.equal(resolveTheme("dark", false), true);
assert.equal(resolveTheme("light", true), false);
assert.equal(resolveTheme(null, true), true);
assert.equal(resolveTheme(null, false), false);
assert.equal(resolveTheme("valore-non-valido", true), true);
console.log("Risoluzione iniziale del tema verificata.");
