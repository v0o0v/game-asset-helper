// M8 — 다크/라이트 모드 수동 토글 (Alpine 컴포넌트 + localStorage 영속화).
//
// 토글 사이클: auto → light → dark → auto ...
//
// auto  = prefers-color-scheme (CSS 미디어쿼리) 따라감
// light = <html data-theme="light"> 강제
// dark  = <html data-theme="dark">  강제
//
// 초기 깜빡임 방지: base.html 의 <head> 인라인 스크립트가 페이지 파싱 직후
// localStorage 값 즉시 적용. 본 Alpine 컴포넌트는 토글 UI + apply() 만.

function themeToggle() {
    return {
        mode: 'auto',
        init() {
            this.mode = localStorage.getItem('assetcache_theme') || 'auto';
            this.apply();
        },
        cycle() {
            this.mode = this.mode === 'auto' ? 'light'
                      : this.mode === 'light' ? 'dark'
                      : 'auto';
            localStorage.setItem('assetcache_theme', this.mode);
            this.apply();
        },
        apply() {
            if (this.mode === 'auto') {
                document.documentElement.removeAttribute('data-theme');
            } else {
                document.documentElement.setAttribute('data-theme', this.mode);
            }
        },
        get icon() {
            return this.mode === 'dark' ? '🌙'
                 : this.mode === 'light' ? '☀️'
                 : '🌗';
        },
        get label() {
            return this.mode === 'dark' ? '다크'
                 : this.mode === 'light' ? '라이트'
                 : '자동';
        },
    };
}
