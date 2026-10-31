/**
 * 永平高中公開授課表件產生器 — Google Apps Script 橋接
 *
 * 部署方式：網頁應用程式，執行身分「我」，存取權「任何人」。
 * 不需要啟用進階服務，也不需要設定指令碼屬性。
 * 第一次貼上後，請先在編輯器上方選「authorize」按「執行」完成授權。
 */

// 與 Streamlit secrets 的 GAS_SECRET 相同
const SECRET = '請改成與 GAS_SECRET 相同的一串亂碼';

const ROOT_FOLDER_ID = '1T6iinnCWOobTse-sJe9YlxvdymcAqMKT'; // 公開授課表件總資料夾
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const GDOC_MIME = 'application/vnd.google-apps.document';

function doPost(e) {
  try {
    const p = JSON.parse(e.postData.contents);
    if (p.secret !== SECRET) return json_({ ok: false, error: 'unauthorized' });
    const fn = ACTIONS[p.action];
    if (!fn) return json_({ ok: false, error: 'unknown action: ' + p.action });
    return json_({ ok: true, result: fn(p) });
  } catch (err) {
    return json_({ ok: false, error: String(err && err.stack || err) });
  }
}

function doGet() {
  return json_({ ok: true, result: 'public-lesson bridge alive' });
}

const ACTIONS = {
  ping: () => 'pong',
  publish: publish_,
};

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/** 第一次部署前在編輯器執行一次，完成雲端硬碟與外部連線授權。 */
function authorize() {
  DriveApp.getFolderById(ROOT_FOLDER_ID).getName();
  UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/about?fields=user', {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
  });
}

/**
 * p.folder：資料夾名稱（例：高-數學-王小明老師）
 * p.name：檔名（不含副檔名）
 * p.docx：Word 檔 base64
 * p.photos：[{name, base64}]（可省略），存到「上課照片」子資料夾
 */
function publish_(p) {
  const root = DriveApp.getFolderById(ROOT_FOLDER_ID);
  const folder = childFolder_(root, p.folder);
  // 同名檔案先移到垃圾桶，重新產生時不會出現重複檔案
  [p.name + '.docx', p.name, p.name + '.pdf'].forEach(function (n) {
    const it = folder.getFilesByName(n);
    while (it.hasNext()) it.next().setTrashed(true);
  });

  const bytes = Utilities.base64Decode(p.docx);
  const docx = folder.createFile(Utilities.newBlob(bytes, DOCX_MIME, p.name + '.docx'));
  const gdocId = convertToGoogleDoc_(bytes, p.name, folder.getId());
  const gdoc = DriveApp.getFileById(gdocId);
  const pdfBlob = gdoc.getAs('application/pdf').setName(p.name + '.pdf');
  const pdf = folder.createFile(pdfBlob);

  (p.photos || []).forEach(function (ph) {
    const sub = childFolder_(folder, '上課照片');
    const old = sub.getFilesByName(ph.name);
    while (old.hasNext()) old.next().setTrashed(true);
    sub.createFile(Utilities.newBlob(Utilities.base64Decode(ph.base64), 'image/jpeg', ph.name));
  });

  return {
    folderUrl: folder.getUrl(),
    docUrl: gdoc.getUrl(),
    docxUrl: docx.getUrl(),
    pdfUrl: pdf.getUrl(),
    pdf: Utilities.base64Encode(pdfBlob.getBytes()),
  };
}

function childFolder_(parent, name) {
  const it = parent.getFoldersByName(name);
  return it.hasNext() ? it.next() : parent.createFolder(name);
}

/** 用 Drive API 上傳 Word 並轉成 Google 文件（不需啟用進階服務）。 */
function convertToGoogleDoc_(bytes, name, folderId) {
  const boundary = 'publiclesson' + Date.now();
  const meta = { name: name, mimeType: GDOC_MIME, parents: [folderId] };
  const head = Utilities.newBlob(
    '--' + boundary + '\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n' +
    JSON.stringify(meta) + '\r\n--' + boundary + '\r\nContent-Type: ' + DOCX_MIME + '\r\n\r\n').getBytes();
  const tail = Utilities.newBlob('\r\n--' + boundary + '--').getBytes();
  const res = UrlFetchApp.fetch(
    'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id', {
      method: 'post',
      contentType: 'multipart/related; boundary=' + boundary,
      payload: head.concat(bytes).concat(tail),
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      muteHttpExceptions: true,
    });
  if (res.getResponseCode() !== 200) {
    throw new Error('轉成 Google 文件失敗（' + res.getResponseCode() + '）：' + res.getContentText());
  }
  return JSON.parse(res.getContentText()).id;
}
