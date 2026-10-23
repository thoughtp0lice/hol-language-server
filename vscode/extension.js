// VS Code client for the hol-language-server command. It starts the server over
// stdio and passes the hol-light settings as initializationOptions.

const vscode = require("vscode");
const { LanguageClient } = require("vscode-languageclient/node");

// The settings lsp_server.py accepts. Only the ones the user set are sent,
// so the server keeps its own defaults for the rest.
const SERVER_SETTINGS = [
  "path", "rootPaths", "autoIndex", "indexWorkspace",
  "customImports", "customTheorems", "customDefinitions",
];

let client;

function initializationOptions() {
  const config = vscode.workspace.getConfiguration("hol-light");
  const options = {};
  for (const key of SERVER_SETTINGS) {
    const set = config.inspect(key);
    const value = set.workspaceFolderValue ?? set.workspaceValue ?? set.globalValue;
    if (value !== undefined) {
      options[key] = value;
    }
  }
  return options;
}

function createClient() {
  const server = {
    command: vscode.workspace.getConfiguration("hol-light").get("languageServer.command"),
  };
  return new LanguageClient(
    "hol-language-server",
    "HOL Light static lookup",
    { run: server, debug: server },
    {
      documentSelector: [{ scheme: "file", language: "hol-light-ocaml" }],
      initializationOptions: initializationOptions(),
    },
  );
}

async function start() {
  client = createClient();
  await client.start();
}

async function restart() {
  if (client) {
    await client.stop();
    client = undefined;
  }
  await start();
}

function report(error) {
  vscode.window.showErrorMessage(`HOL Light language server: ${error.message}`);
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("hol-light.languageServer.restart", () => restart().catch(report)),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("hol-light")) {
        restart().catch(report);
      }
    }),
  );
  return start().catch(report);
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
