#!/usr/bin/env node
// Validate benchmark TokUI DSL outputs with the upstream parser.

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');
const tokuiParserPath = path.resolve(repoRoot, '..', '_research', 'tokui', 'src', 'core', 'parser.js');
const require = createRequire(import.meta.url);
const { TokUIParser } = require(tokuiParserPath);

const inputPath = process.argv[2] || path.join(repoRoot, 'docs', 'generated', 'tokui-deepseek-benchmark.json');
const absoluteInputPath = path.resolve(process.cwd(), inputPath);

function readInput(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  if (filePath.endsWith('.json')) {
    const json = JSON.parse(raw);
    if (Array.isArray(json.results)) {
      return json.results.map((result, index) => ({
        name: `${result.prompt_name || 'result'}#${result.run_index || index + 1}`,
        dsl: result.output_text || '',
      }));
    }
  }
  return [{ name: path.basename(filePath), dsl: raw }];
}

function walk(node, visit) {
  visit(node);
  for (const child of node.children || []) walk(child, visit);
}

function validateOne(item) {
  const warnings = [];
  const nodes = [];
  const previousWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(' '));
  try {
    const parser = new TokUIParser((node) => nodes.push(node));
    parser.parse(item.dsl);
  } finally {
    console.warn = previousWarn;
  }

  const invalidTypes = [];
  const allTypes = [];
  for (const node of nodes) {
    walk(node, (current) => {
      allTypes.push(current.type);
      if (
        current.type !== '_text'
        && !/^[a-z][a-z0-9-]*$/.test(current.type)
      ) {
        invalidTypes.push(current.type);
      }
    });
  }

  const flags = {
    empty: item.dsl.trim().length === 0,
    codeFence: item.dsl.includes('```'),
    bracketBalance: item.dsl.split('[').length - item.dsl.split(']').length,
    equalsAttrs: /\[[a-z][a-z0-9-]*(?:\s+[a-z][\w-]*:(?:"[^"]*"|[^\s\]]+))*\s+[a-z][\w-]*=/.test(item.dsl),
    htmlTableTags: /\[\/?(?:th|td)\b/.test(item.dsl),
    invalidLeafClosings: (
      item.dsl.match(/\[\/(?:h[1-6]|btn|input|pwd|source|suggestion|chart|thead|tr|opt)\]/g) || []
    ).length,
  };

  return {
    name: item.name,
    ok: !flags.empty
      && !flags.codeFence
      && flags.bracketBalance === 0
      && !flags.equalsAttrs
      && !flags.htmlTableTags
      && flags.invalidLeafClosings === 0
      && warnings.length === 0
      && invalidTypes.length === 0,
    flags,
    warnings,
    invalidTypes: [...new Set(invalidTypes)],
    rootTypes: nodes.map((node) => node.type),
    allTypes: [...new Set(allTypes)].sort(),
  };
}

const items = readInput(absoluteInputPath);
const reports = items.map(validateOne);
const failed = reports.filter((report) => !report.ok);

for (const report of reports) {
  const status = report.ok ? 'OK' : 'FAIL';
  console.log(`${status} ${report.name}`);
  if (!report.ok) {
    console.log(JSON.stringify({
      flags: report.flags,
      warnings: report.warnings,
      invalidTypes: report.invalidTypes,
      rootTypes: report.rootTypes,
    }, null, 2));
  }
}

console.log(JSON.stringify({
  total: reports.length,
  ok: reports.length - failed.length,
  failed: failed.length,
}, null, 2));

process.exit(failed.length === 0 ? 0 : 1);
