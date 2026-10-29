//! Okno „Mózg Hermesa” — natywne okno WebKitGTK dla serwera Mózgu (domyślnie http://127.0.0.1:8110).
//! Cały wygląd i czat są na serwerze, okno tylko je pokazuje.
//!
//! - słownik pisowni (hunspell pl_PL + en_US) w polach tekstowych,
//! - mikrofon bez pytania (strona serwera Mózgu), linki obce → zwykła przeglądarka,
//! - bez belki: chwyć górny pas strony = przesuń, dwuklik = maksymalizuj; Ctrl+W/Ctrl+Q zamknij
//! - Ctrl+R odśwież, Ctrl +/−/0 powiększenie,
//! - serwer nie odpowiada → ponawia co 3 s.
//!
//! Adres serwera: zmienna środowiskowa `MOZG_ADRES` (np. `http://127.0.0.1:8110`).
//! `mozg-okno --instaluj` kładzie ikonę i wpis w menu (~/.local/share).
use gtk::glib;
use gtk::prelude::*;
use std::cell::Cell;
use std::rc::Rc;
use webkit2gtk::{
    LoadEvent, PermissionRequestExt, SettingsExt, UserContentInjectedFrames, UserContentManager,
    UserContentManagerExt, UserMediaPermissionRequest, UserScript, UserScriptInjectionTime, WebContext,
    WebContextExt, WebView, WebViewExt,
};

// Bez belki GTK — okno przesuwa się chwytem za górny pas strony (nagłówek Mózgu), dwuklik = maksymalizuj.
const CSS: &str = "
.mozg-pasek { min-height: 0; padding: 0; margin: 0; border: 0; background: transparent; box-shadow: none; }
decoration { border-radius: 0; box-shadow: 0 0 0 1px #2a2a2a, 0 6px 22px rgba(0,0,0,.6); }
window.csd, window.csd > * { border-radius: 0; }
";
const SKRYPT: &str = r#"(function(){
  const PAS = 64; // px od góry strony = uchwyt okna
  const klikalne = 'button,a,input,textarea,select,label,[role=button],[onclick],[contenteditable]';
  const h = n => window.webkit && window.webkit.messageHandlers[n] && window.webkit.messageHandlers[n].postMessage('');
  document.addEventListener('mousedown', e => {
    if (e.button !== 0 || e.clientY > PAS || e.detail > 1 || e.target.closest(klikalne)) return;
    h('przesun');
  }, true);
  document.addEventListener('dblclick', e => {
    if (e.clientY > PAS || e.target.closest(klikalne)) return;
    h('max');
  }, true);
})();"#;

fn app_id() -> &'static str {
    "io.github.longer54.MozgHermesa"
}

fn serwer() -> &'static str {
    static S: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    S.get_or_init(|| std::env::var("MOZG_ADRES").unwrap_or_else(|_| "http://127.0.0.1:8110".into()))
}

const IKONY: [(u32, &[u8]); 8] = [
    (16, include_bytes!("../ikona/mozg-16.png")),
    (22, include_bytes!("../ikona/mozg-22.png")),
    (24, include_bytes!("../ikona/mozg-24.png")),
    (32, include_bytes!("../ikona/mozg-32.png")),
    (48, include_bytes!("../ikona/mozg-48.png")),
    (64, include_bytes!("../ikona/mozg-64.png")),
    (128, include_bytes!("../ikona/mozg-128.png")),
    (256, include_bytes!("../ikona/mozg-256.png")),
];

fn instaluj() -> std::io::Result<()> {
    let dane = glib::user_data_dir();
    for (r, png) in IKONY {
        let kat = dane.join(format!("icons/hicolor/{r}x{r}/apps"));
        std::fs::create_dir_all(&kat)?;
        std::fs::write(kat.join("mozg-hermesa.png"), png)?;
    }
    let bin = glib::home_dir().join(".local/bin/mozg-okno");
    let apps = dane.join("applications");
    std::fs::create_dir_all(&apps)?;
    for (plik, nazwa, opis, arg, id) in [
        ("mozg-hermesa.desktop", "Mózg Hermesa", "Na żywo: co robią agenci Hermesa", "", "io.github.longer54.MozgHermesa"),
    ] {
        let wpis = format!(
            "[Desktop Entry]\nType=Application\nName={nazwa}\nComment={opis}\n\
             Exec={}{arg}\nIcon=mozg-hermesa\nCategories=Utility;\nStartupWMClass={id}\nTerminal=false\n",
            bin.display()
        );
        std::fs::write(apps.join(plik), wpis)?;
    }
    let _ = std::process::Command::new("gtk-update-icon-cache")
        .args(["-q", "-t", &dane.join("icons/hicolor").to_string_lossy()])
        .status();
    Ok(())
}

fn build_window(app: &gtk::Application) -> gtk::ApplicationWindow {
    let ctx = WebContext::default().expect("WebContext");
    // Słownik pisowni (hunspell) — polski i angielski.
    ctx.set_spell_checking_enabled(true);
    ctx.set_spell_checking_languages(&["pl_PL", "en_US"]);
    let ucm = UserContentManager::new();
    ucm.register_script_message_handler("przesun");
    ucm.register_script_message_handler("max");
    ucm.add_script(&UserScript::new(SKRYPT, UserContentInjectedFrames::TopFrame, UserScriptInjectionTime::End, &[], &[]));
    let webview: WebView = glib::Object::builder().property("web-context", &ctx).property("user-content-manager", &ucm).build();
    if let Some(ust) = WebViewExt::settings(&webview) {
        ust.set_enable_media_stream(true);
        ust.set_enable_mediasource(true);
        ust.set_media_playback_requires_user_gesture(false);
        ust.set_enable_webgl(true);
        ust.set_hardware_acceleration_policy(webkit2gtk::HardwareAccelerationPolicy::Always);
    }
    webview.connect_permission_request(|_, req| {
        if req.downcast_ref::<UserMediaPermissionRequest>().is_some() {
            req.allow();
            return true;
        }
        false
    });
    webview.load_uri(&format!("{}/", serwer()));

    webview.connect_load_failed(move |wv, _ev: LoadEvent, uri, _err| {
        if !uri.starts_with(serwer()) {
            return false;
        }
        let wv = wv.clone();
        let uri = uri.to_string();
        glib::timeout_add_seconds_local_once(3, move || wv.load_uri(&uri));
        true
    });

    // Linki spoza serwera Mózgu → domyślna przeglądarka.
    webview.connect_decide_policy(|_, decyzja, typ| {
        use webkit2gtk::{NavigationPolicyDecision, NavigationPolicyDecisionExt, PolicyDecisionExt, PolicyDecisionType, URIRequestExt};
        if typ != PolicyDecisionType::NavigationAction && typ != PolicyDecisionType::NewWindowAction {
            return false;
        }
        let Some(nd) = decyzja.downcast_ref::<NavigationPolicyDecision>() else { return false };
        let Some(uri) = nd.navigation_action().and_then(|a| a.request()).and_then(|r| r.uri()) else { return false };
        if uri.starts_with(serwer()) || !uri.starts_with("http") {
            return false;
        }
        let _ = gtk::gio::AppInfo::launch_default_for_uri(&uri, None::<&gtk::gio::AppLaunchContext>);
        decyzja.ignore();
        true
    });

    let window = gtk::ApplicationWindow::new(app);
    window.set_title("Mózg Hermesa");
    window.set_icon_name(Some("mozg-hermesa"));
    window.set_default_size(1400, 900);
    let pasek = gtk::Box::new(gtk::Orientation::Horizontal, 0);
    pasek.style_context().add_class("mozg-pasek");
    window.set_titlebar(Some(&pasek));
    let css = gtk::CssProvider::new();
    if css.load_from_data(CSS.as_bytes()).is_ok() {
        if let Some(ekran) = gtk::prelude::WidgetExt::screen(&window) {
            gtk::StyleContext::add_provider_for_screen(&ekran, &css, gtk::STYLE_PROVIDER_PRIORITY_APPLICATION);
        }
    }
    let klik: Rc<Cell<Option<(u32, f64, f64, u32)>>> = Rc::new(Cell::new(None));
    let klik2 = klik.clone();
    webview.connect_button_press_event(move |_, ev| {
        let (x, y) = ev.root();
        klik2.set(Some((ev.button(), x, y, ev.time())));
        glib::Propagation::Proceed
    });
    let slabe = window.downgrade();
    ucm.connect_script_message_received(Some("przesun"), move |_, _| {
        if let (Some(win), Some((b, x, y, t))) = (slabe.upgrade(), klik.get()) {
            win.begin_move_drag(b as i32, x as i32, y as i32, t);
        }
    });
    let slabe = window.downgrade();
    ucm.connect_script_message_received(Some("max"), move |_, _| {
        if let Some(win) = slabe.upgrade() {
            if win.is_maximized() { win.unmaximize() } else { win.maximize() }
        }
    });
    window.add(&webview);

    let wv = webview.clone();
    window.connect_key_press_event(move |win, ev| {
        use gtk::gdk::keys::constants as key;
        if ev.keyval() == key::F11 {
            let pelny = win.window().is_some_and(|g| g.state().contains(gtk::gdk::WindowState::FULLSCREEN));
            if pelny { win.unfullscreen() } else { win.fullscreen() }
            return glib::Propagation::Stop;
        }
        if !ev.state().contains(gtk::gdk::ModifierType::CONTROL_MASK) {
            return glib::Propagation::Proceed;
        }
        match ev.keyval() {
            key::r | key::R => wv.reload_bypass_cache(),
            key::w | key::W | key::q | key::Q => {
                if let Some(app) = win.application() {
                    app.quit();
                }
            }
            key::plus | key::equal | key::KP_Add => wv.set_zoom_level(wv.zoom_level() + 0.1),
            key::minus | key::KP_Subtract => wv.set_zoom_level((wv.zoom_level() - 0.1).max(0.3)),
            key::_0 | key::KP_0 => wv.set_zoom_level(1.0),
            _ => return glib::Propagation::Proceed,
        }
        glib::Propagation::Stop
    });
    window
}

fn main() {
    if std::env::args().any(|a| a == "--instaluj") {
        if let Err(e) = instaluj() {
            eprintln!("mozg-okno --instaluj: {e}");
            std::process::exit(1);
        }
        return;
    }
    glib::set_prgname(Some(app_id()));
    let app = gtk::Application::new(Some(app_id()), gtk::gio::ApplicationFlags::empty());
    // Druga instancja = pokaż istniejące okno.
    app.connect_activate(|app| {
        if let Some(w) = app.windows().first() {
            w.present();
            return;
        }
        let win = build_window(app);
        win.show_all();
        win.present();
    });
    app.run_with_args::<&str>(&[]);
}
