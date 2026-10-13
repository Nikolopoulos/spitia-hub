import Cocoa
import Foundation

class SpitiaMenuBarApp: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    var timer: Timer?
    let statusFilePath = "/Volumes/Terataki/projects/spitia/alert_status.json"
    let pythonScriptPath = "/Volumes/Terataki/projects/spitia/auto_pipeline.py"

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        updateStatusItemUI()

        // Timer to refresh status item every 10 seconds
        timer = Timer.scheduledTimer(withTimeInterval: 10.0, repeats: true) { [weak self] _ in
            self?.updateStatusItemUI()
        }
    }

    func updateStatusItemUI() {
        var lastRun = "Ποτέ"
        var newCount = 0

        if let data = try? Data(contentsOf: URL(fileURLWithPath: statusFilePath)),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            lastRun = json["last_run"] as? String ?? "Ποτέ"
            newCount = json["new_properties_count"] as? Int ?? 0
        }

        if let button = statusItem.button {
            if newCount > 0 {
                button.title = "🏠 \(newCount) νέα!"
            } else {
                button.title = "🏠 Spitia"
            }
        }

        let menu = NSMenu()
        
        let titleItem = NSMenuItem(title: "🏠 Spitia Alert Monitor", action: nil, keyEquivalent: "")
        titleItem.isEnabled = false
        menu.addItem(titleItem)
        menu.addItem(NSMenuItem.separator())

        let lastRunItem = NSMenuItem(title: "⏱ Τελευταίος έλεγχος: \(lastRun)", action: nil, keyEquivalent: "")
        lastRunItem.isEnabled = false
        menu.addItem(lastRunItem)

        let countItem = NSMenuItem(title: "✨ Νέα ακίνητα (τελευταίο run): \(newCount)", action: nil, keyEquivalent: "")
        countItem.isEnabled = false
        menu.addItem(countItem)

        menu.addItem(NSMenuItem.separator())
        
        let runNowItem = NSMenuItem(title: "🔄 Έλεγχος τώρα", action: #selector(runCheckNow), keyEquivalent: "r")
        runNowItem.target = self
        menu.addItem(runNowItem)

        let openFolderItem = NSMenuItem(title: "📂 Άνοιγμα φακέλου", action: #selector(openFolder), keyEquivalent: "o")
        openFolderItem.target = self
        menu.addItem(openFolderItem)

        menu.addItem(NSMenuItem.separator())
        
        let quitItem = NSMenuItem(title: "Έξοδος", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
    }

    @objc func runCheckNow() {
        if let button = statusItem.button {
            button.title = "🏠 ⏳..."
        }
        DispatchQueue.global(qos: .background).async {
            let task = Process()
            task.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            task.arguments = [self.pythonScriptPath]
            try? task.run()
            task.waitUntilExit()

            DispatchQueue.main.async { [weak self] in
                self?.updateStatusItemUI()
            }
        }
    }

    @objc func openFolder() {
        NSWorkspace.shared.open(URL(fileURLWithPath: "/Volumes/Terataki/projects/spitia"))
    }

    @objc func quitApp() {
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory) // Hides from Dock, lives purely in Menu Bar!
let delegate = SpitiaMenuBarApp()
app.delegate = delegate
app.run()
