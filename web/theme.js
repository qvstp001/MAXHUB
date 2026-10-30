'use strict';
(() => {
  // Migrate only known display preferences from the previous project name.
  try {
    for(const key of ['theme','layout','density','sidebar','player']) {
      const previous=localStorage.getItem('qmaxhub.'+key);
      if(localStorage.getItem('maxhub.'+key)===null&&previous!==null)localStorage.setItem('maxhub.'+key,previous);
    }
  } catch {}
  const system = matchMedia('(prefers-color-scheme: dark)');
  function apply(choice) {
    const dark = choice === 'dark' || (choice !== 'light' && system.matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#080A0D' : '#FFFFFF');
  }
  function preference() { try { return localStorage.getItem('maxhub.theme') || 'system'; } catch { return 'system'; } }
  window.setLibraryTheme = choice => {
    try { localStorage.setItem('maxhub.theme', choice); } catch {}
    apply(choice);
  };
  system.addEventListener('change', () => apply(preference()));
  apply(preference());
})();
