// A plain Electron window for the release checks, standing in for apps like Claude Desktop.
// The page is one strong colour with a dark tag in the top-left corner, so leftover pieces
// and content that drifts away from the corner are easy to find in screenshots.
const { app, BrowserWindow } = require('electron');
const path = require('path');

app.whenReady().then(() => {
    // LGQA_LIKE_CLAUDE=1: open like Claude Desktop does: no window frame, made hidden and
    // shown once the page has drawn. LGQA_MAXIMIZE_AFTER_MS: then maximize it that long
    // after it shows, while it is still opening (Claude coming back maximized).
    const like = process.env.LGQA_LIKE_CLAUDE === '1';
    const win = new BrowserWindow({
        width: 760, height: 480, x: 120, y: 120,
        title: process.env.LGQA_TITLE || 'LGQA Electron',
        backgroundColor: '#f000c8',
        frame: !like,
        show: !like,
        webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false },
    });
    if (like) {
        // Hidden windows may never draw (and so never get ready-to-show) without a GPU.
        const show = () => {
            if (win.isDestroyed() || win.isVisible())
                return;
            win.show();
            const later = Number(process.env.LGQA_MAXIMIZE_AFTER_MS || 0);
            if (later)
                setTimeout(() => win.maximize(), later);
        };
        win.once('ready-to-show', show);
        win.webContents.once('did-finish-load', () => setTimeout(show, 300));
    }
    win.on('page-title-updated', e => e.preventDefault());   // keep the title above
    // LGQA_BUSY=1: keep adding text, like an app streaming an answer.
    win.loadFile(path.join(__dirname, 'index.html'), { query: { busy: process.env.LGQA_BUSY || '0' } });
});
app.on('window-all-closed', () => app.quit());
