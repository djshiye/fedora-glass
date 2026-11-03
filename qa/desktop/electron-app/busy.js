// With ?busy=1 the page keeps writing words, the way a chat app streams an answer.
if (new URLSearchParams(location.search).get('busy') === '1') {
    const box = document.getElementById('stream');
    let n = 0;
    setInterval(() => {
        box.textContent += `word${n++} `;
        if (box.textContent.length > 4000) box.textContent = '';
    }, 40);
}
