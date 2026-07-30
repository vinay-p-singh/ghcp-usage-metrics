// Copies the Python extractor into the extension so a packaged .vsix is
// self-contained (findRepoRoot falls back to <extension>/py/usage.py).
const fs = require("fs");
const path = require("path");

const repo = path.resolve(__dirname, "..", ".."); // extension/scripts -> extension -> repo root
const dest = path.resolve(__dirname, "..", "py");
const files = ["usage.py", "build_dashboard.py"];
// ghcp: pure-helper package imported by usage.py
// web:  css/html/js the dashboard template assembles at import time
const packages = [
  { name: "ghcp", required: true },
  { name: "web", required: false }
];
const skipDirs = new Set(["__pycache__", "out", ".cache"]);

fs.mkdirSync(dest, { recursive: true });
for (const f of files) {
  const src = path.join(repo, f);
  if (!fs.existsSync(src)) {
    console.error(`bundle: missing ${src}`);
    process.exit(1);
  }
  fs.copyFileSync(src, path.join(dest, f));
  console.log(`bundle: ${f} -> py/${f}`);
}

function copyDir(srcDir, destDir, label) {
  fs.mkdirSync(destDir, { recursive: true });
  for (const entry of fs.readdirSync(srcDir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (skipDirs.has(entry.name)) {
        continue;
      }
      copyDir(path.join(srcDir, entry.name), path.join(destDir, entry.name),
              `${label}/${entry.name}`);
      continue;
    }
    if (entry.name.endsWith(".pyc")) {
      continue;
    }
    fs.copyFileSync(path.join(srcDir, entry.name), path.join(destDir, entry.name));
    console.log(`bundle: ${label}/${entry.name} -> py/${label}/${entry.name}`);
  }
}

for (const pkg of packages) {
  const srcDir = path.join(repo, pkg.name);
  if (!fs.existsSync(srcDir)) {
    if (pkg.required) {
      console.error(`bundle: missing package ${srcDir}`);
      process.exit(1);
    }
    continue;
  }
  copyDir(srcDir, path.join(dest, pkg.name), pkg.name);
}

