import PhotosUI
import SwiftUI

@main
struct LanPhotoTransferApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    @AppStorage("receiverHost") private var receiverHost = ""
    @State private var selection: [PhotosPickerItem] = []
    @State private var message = "Enter the laptop's Wi-Fi address, then choose media."
    @State private var sending = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Windows laptop") {
                    TextField("Example: 192.168.1.25", text: $receiverHost)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.decimalPad)
                    Text("Keep the Windows receiver open and connect both devices to the same Wi-Fi.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Photos and videos") {
                    PhotosPicker(selection: $selection, maxSelectionCount: 30,
                                 matching: .any(of: [.images, .videos])) {
                        Label("Choose photos or videos", systemImage: "photo.on.rectangle.angled")
                    }
                    Text(selection.isEmpty ? "Nothing selected" : "\(selection.count) item(s) selected")
                        .foregroundStyle(.secondary)
                    Button {
                        Task { await sendSelection() }
                    } label: {
                        if sending { ProgressView("Sending…") }
                        else { Label("Send to laptop", systemImage: " paperplane.fill") }
                    }
                    .disabled(sending || selection.isEmpty || receiverHost.trimmingCharacters(in: .whitespaces).isEmpty)
                    Text(message).font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("LAN Photo Transfer")
        }
    }

    @MainActor
    private func sendSelection() async {
        let host = receiverHost.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let urlHost = URL(string: "http://\(host):8765")?.host, urlHost == host else {
            message = "Enter a valid laptop IPv4 address, such as 192.168.1.25."
            return
        }
        sending = true
        defer { sending = false }
        var completed = 0
        for item in selection {
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    throw TransferError.unreadable
                }
                let filename = safeFilename(item.suggestedName ?? "media-\(completed + 1).jpg")
                var components = URLComponents(string: "http://\(host):8765/upload")!
                components.queryItems = [URLQueryItem(name: "filename", value: filename)]
                var request = URLRequest(url: components.url!)
                request.httpMethod = "PUT"
                request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
                request.setValue(String(data.count), forHTTPHeaderField: "Content-Length")
                let (_, response) = try await URLSession.shared.upload(for: request, from: data)
                guard let http = response as? HTTPURLResponse, http.statusCode == 201 else {
                    throw TransferError.serverRejected
                }
                completed += 1
                message = "Sent \(completed) of \(selection.count)…"
            } catch {
                message = "Stopped after \(completed) file(s): \(error.localizedDescription)"
                return
            }
        }
        message = "Finished: \(completed) file(s) sent."
        selection = []
    }

    private func safeFilename(_ input: String) -> String {
        let name = URL(fileURLWithPath: input).lastPathComponent
            .replacingOccurrences(of: "?", with: "_")
            .replacingOccurrences(of: "&", with: "_")
        return name.isEmpty ? "media.jpg" : name
    }
}

enum TransferError: LocalizedError {
    case unreadable, serverRejected
    var errorDescription: String? {
        switch self {
        case .unreadable: return "Could not read one selected item."
        case .serverRejected: return "The Windows receiver rejected the upload."
        }
    }
}
