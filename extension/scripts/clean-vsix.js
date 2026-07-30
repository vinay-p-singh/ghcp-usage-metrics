// Remove previously built .vsix files before packaging a new one.
//
// Old builds otherwise pile up next to the new one, and every install task that
// picks "the newest file" is one clock skew away from shipping the wrong build.
// Keeping exactly one .vsix in the folder makes that impossible.
const fs = require("node:fs");
const path = require("node:path");

const dir = path.join(__dirname, "..");
for (const name of fs.readdirSync(dir)) {
  if (!name.endsWith(".vsix")) continue;
  fs.unlinkSync(path.join(dir, name));
  console.log("removed stale package " + name);
}
