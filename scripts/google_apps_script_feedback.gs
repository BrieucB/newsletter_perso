const SHEET_NAME = "feedback";
const SHARED_SECRET = "replace-me";

function doGet(e) {
  const payloadToken = e.parameter.payload || "";
  const signature = e.parameter.signature || "";

  if (!payloadToken || !signature) {
    return htmlResponse("Missing feedback payload.", null);
  }

  let payload;
  try {
    payload = verifySignedPayload(payloadToken, signature);
  } catch (error) {
    return htmlResponse("This feedback link is invalid.", null);
  }

  const action = payload.action;
  if (action === "vote") {
    return handleVote(payload);
  }
  if (action === "sync") {
    return handleSync();
  }
  return htmlResponse("Unknown feedback action.", null);
}

function handleVote(payload) {
  const expiresAt = new Date(payload.expires_at);
  if (expiresAt.getTime() < Date.now()) {
    return htmlResponse("This feedback link has expired.", payload.source_url || null);
  }

  const sheet = ensureSheet();
  sheet.appendRow([
    Utilities.getUuid(),
    payload.issue_id,
    payload.item_id,
    payload.vote,
    payload.recipient_key,
    payload.subject || "",
    payload.item_title || "",
    payload.source_url || "",
    new Date().toISOString(),
  ]);

  const voteLabel = payload.vote === "+" ? "+ good rec" : "- bad rec";
  return htmlResponse("Recorded feedback: " + voteLabel, payload.source_url || null);
}

function handleSync() {
  const sheet = ensureSheet();
  const values = sheet.getDataRange().getValues();
  if (values.length <= 1) {
    return jsonResponse({ events: [] });
  }

  const header = values[0];
  const events = values.slice(1).map((row) => {
    const event = {};
    header.forEach((key, index) => {
      event[key] = row[index];
    });
    return event;
  });
  return jsonResponse({ events: events });
}

function ensureSheet() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      "external_event_id",
      "issue_id",
      "item_id",
      "vote",
      "recipient_key",
      "subject",
      "item_title",
      "source_url",
      "created_at",
    ]);
  }
  return sheet;
}

function verifySignedPayload(payloadToken, signature) {
  const expectedSignature = toHex(
    Utilities.computeHmacSha256Signature(payloadToken, SHARED_SECRET),
  );
  if (expectedSignature !== signature) {
    throw new Error("Invalid signature.");
  }
  const decoded = Utilities.newBlob(
    Utilities.base64DecodeWebSafe(payloadToken),
  ).getDataAsString();
  return JSON.parse(decoded);
}

function toHex(bytes) {
  return bytes
    .map((value) => {
      const normalized = value < 0 ? value + 256 : value;
      return ("0" + normalized.toString(16)).slice(-2);
    })
    .join("");
}

function htmlResponse(message, sourceUrl) {
  const sourceLink = sourceUrl
    ? `<p style="margin-top:16px;"><a href="${sourceUrl}">Open source article</a></p>`
    : "";
  const html = `
    <html>
      <body style="font-family:Georgia,serif;background:#f5f4ef;padding:32px;">
        <div style="max-width:560px;margin:0 auto;background:#fffdf8;border:1px solid #ded6c9;border-radius:12px;padding:24px;">
          <p style="margin:0 0 12px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#8b6f47;">Feedback</p>
          <h1 style="margin:0 0 12px;font-size:24px;color:#102a43;">Thanks</h1>
          <p style="margin:0;font-size:16px;line-height:1.6;color:#334e68;">${message}</p>
          ${sourceLink}
        </div>
      </body>
    </html>
  `;
  return HtmlService.createHtmlOutput(html);
}

function jsonResponse(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(
    ContentService.MimeType.JSON,
  );
}
