document.addEventListener('DOMContentLoaded', () => {
  // Loading state for all forms
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('[type="submit"]');
      if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Processing…';
      }
      const overlay = document.getElementById('loading-overlay');
      if (overlay) overlay.style.display = 'flex';
    });
  });

  // Client-side file type validation
  document.querySelectorAll('input[type="file"]').forEach(input => {
    input.addEventListener('change', () => {
      const file = input.files[0];
      if (!file) return;
      const ok = /\.(csv|xlsx|xls|txt)$/i.test(file.name);
      if (!ok) {
        alert(`Invalid file: "${file.name}". Please upload .csv, .xlsx, or .txt`);
        input.value = '';
      }
    });
  });
});
