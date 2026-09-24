import { readdir, readFile, stat } from "node:fs/promises";
import { extname, relative, resolve } from "node:path";

const root = process.cwd();
const dist = resolve(root, "dist");
const source = resolve(root, "src");
const failures = [];

async function filesUnder(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  }));
  return nested.flat();
}

function reject(condition, message) {
  if (condition) failures.push(message);
}

const index = await readFile(resolve(dist, "index.html"), "utf8");
reject(/<script(?![^>]*\bsrc\s*=)[^>]*>[\s\S]*?<\/script\s*>/i.test(index), "index.html contiene uno script inline");
reject(/<style\b/i.test(index), "index.html contiene un blocco style inline");
reject(/\sstyle\s*=/i.test(index), "index.html contiene un attributo style");
reject(
  /<(?:script|link)\b[^>]*(?:src|href)\s*=\s*["']https?:/i.test(index),
  "index.html carica uno script o un foglio stile remoto",
);
reject(!/<script\s+src=["']\/theme-init\.js["']><\/script>/i.test(index), "theme-init.js non viene caricato prima del bundle");

const sourceFiles = (await filesUnder(source)).filter((path) => [".ts", ".tsx", ".html"].includes(extname(path)));
for (const path of sourceFiles) {
  const contents = await readFile(path, "utf8");
  reject(/\bstyle\s*=/.test(contents), `${relative(root, path)} contiene un attributo style`);
}

const distFiles = await filesUnder(dist);
for (const path of distFiles.filter((item) => [".html", ".css", ".js"].includes(extname(item)))) {
  const contents = await readFile(path, "utf8");
  reject(/fonts\.(?:googleapis|gstatic)\.com/i.test(contents), `${relative(root, path)} contiene un URL Google Fonts`);
  if (extname(path) === ".css") {
    reject(/url\(\s*["']?https?:\/\//i.test(contents), `${relative(root, path)} contiene una risorsa CSS remota`);
  }
}

for (const path of [
  "theme-init.js",
  "licenses/Inter-OFL-1.1.txt",
  "licenses/JetBrains-Mono-OFL-1.1.txt",
  "licenses/Material-Symbols-Apache-2.0.txt",
]) {
  try {
    reject(!(await stat(resolve(dist, path))).isFile(), `${path} non e un file del build`);
  } catch {
    failures.push(`${path} manca dal build`);
  }
}

const woff2Files = distFiles.filter((path) => extname(path) === ".woff2");
reject(woff2Files.length < 3, "il build non contiene tutti i font WOFF2 locali richiesti");

if (failures.length) {
  console.error("Controllo CSP del build non riuscito:\n- " + failures.join("\n- "));
  process.exit(1);
}
console.log(`Controllo CSP superato: ${woff2Files.length} font WOFF2 locali, nessuna risorsa incompatibile.`);
