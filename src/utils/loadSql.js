const fs = require("fs");
const path = require("path");

function loadSql(fileName) {
  const filePath = path.join(__dirname, "../db/queries", fileName);
  return fs.readFileSync(filePath, "utf8");
}

module.exports = { loadSql };
