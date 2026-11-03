// A plain Electron window for the release checks, standing in for apps like Claude Desktop.
// The page is one strong colour with a dark tag in the top-left corner, so leftover pieces
// and content that drifts away from the corner are easy to find in screenshots.
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.whenReady().then(() => {
    const win = new BrowserWindow({
        width: 760, height: 480, x: 120, y: 120,
        title: process.env.LGQA_TITLE || 'LGQA Electron',
        backgroundColor: '#f000c8',
        webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false },
    });
    win.on('page-title-updated', e => e.preventDefault());   // keep the title above
    // LGQA_BUSY=1: keep adding text, like an app streaming an answer.
    win.loadFile(path.join(__dirname, 'index.html'), { query: { busy: process.env.LGQA_BUSY || '0' } });
});
app.on('window-all-closed', () => app.quit());
