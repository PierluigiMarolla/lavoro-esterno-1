import { copyFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const destination = resolve(root, "dist", "licenses");
const licenses = [
  ["@fontsource/inter/LICENSE", "Inter-OFL-1.1.txt"],
  ["@fontsource/jetbrains-mono/LICENSE", "JetBrains-Mono-OFL-1.1.txt"],
  ["material-symbols/LICENSE", "Material-Symbols-Apache-2.0.txt"],
];

await mkdir(destination, { recursive: true });
for (const [source, target] of licenses) {
  await copyFile(resolve(root, "node_modules", source), resolve(destination, target));
}
console.log("Licenze dei font copiate nel build.");
