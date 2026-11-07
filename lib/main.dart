import 'dart:convert';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() => runApp(const VoiceCloneApp());

class VoiceCloneApp extends StatelessWidget {
  const VoiceCloneApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Voice Clone',
        theme: ThemeData(
            colorSchemeSeed: Colors.deepPurple,
            useMaterial3: true,
            brightness: Brightness.dark),
        home: const Home(),
      );
}

class Voice {
  final String id, name;
  Voice(this.id, this.name);
}

class Home extends StatefulWidget {
  const Home({super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  int tab = 0;
  String server = 'http://10.0.2.2:8000';
  String apiKey = '';
  List<Voice> voices = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final p = await SharedPreferences.getInstance();
    server = p.getString('server') ?? server;
    apiKey = p.getString('key') ?? '';
    await refresh();
  }

  Map<String, String> get headers => {if (apiKey.isNotEmpty) 'X-API-Key': apiKey};
  Uri url(String path) => Uri.parse('${server.replaceAll(RegExp(r'/+$'), '')}$path');

  void toast(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> refresh() async {
    try {
      final r = await http.get(url('/voices'), headers: headers);
      if (r.statusCode == 200) {
        final list = jsonDecode(r.body) as List;
        setState(() => voices =
            list.map((e) => Voice(e['id'], e['name'])).toList());
      } else {
        toast('Server error ${r.statusCode}');
      }
    } catch (e) {
      toast('Cannot reach server. Check Settings.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      CloneTab(home: this),
      SpeakTab(home: this),
      SettingsTab(home: this),
    ];
    return Scaffold(
      appBar: AppBar(title: const Text('Voice Clone')),
      body: pages[tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.mic), label: 'Clone'),
          NavigationDestination(icon: Icon(Icons.graphic_eq), label: 'Speak'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}

class CloneTab extends StatefulWidget {
  final _HomeState home;
  const CloneTab({super.key, required this.home});
  @override
  State<CloneTab> createState() => _CloneTabState();
}

class _CloneTabState extends State<CloneTab> {
  final nameCtl = TextEditingController();
  final rec = AudioRecorder();
  String? samplePath;
  bool recording = false, consent = false, busy = false;

  Future<void> pick() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.audio);
    if (r?.files.single.path != null) {
      setState(() => samplePath = r!.files.single.path);
    }
  }

  Future<void> toggleRecord() async {
    if (recording) {
      final p = await rec.stop();
      setState(() {
        recording = false;
        samplePath = p;
      });
      return;
    }
    if (!await rec.hasPermission()) {
      widget.home.toast('Microphone permission denied');
      return;
    }
    final dir = await getTemporaryDirectory();
    await rec.start(const RecordConfig(encoder: AudioEncoder.wav),
        path: '${dir.path}/sample_${DateTime.now().millisecondsSinceEpoch}.wav');
    setState(() => recording = true);
  }

  Future<void> upload() async {
    final h = widget.home;
    if (samplePath == null || nameCtl.text.trim().isEmpty) {
      h.toast('Add a name and a voice sample');
      return;
    }
    setState(() => busy = true);
    try {
      final req = http.MultipartRequest('POST', h.url('/clone'))
        ..headers.addAll(h.headers)
        ..fields['name'] = nameCtl.text.trim()
        ..fields['consent'] = consent.toString()
        ..files.add(await http.MultipartFile.fromPath('file', samplePath!));
      final res = await http.Response.fromStream(await req.send());
      if (res.statusCode == 200) {
        h.toast('Voice saved');
        nameCtl.clear();
        setState(() {
          samplePath = null;
          consent = false;
        });
        await h.refresh();
      } else {
        h.toast(jsonDecode(res.body)['detail']?.toString() ?? 'Failed');
      }
    } catch (e) {
      h.toast('Upload failed: $e');
    }
    setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Use 10-60 seconds of clean speech, no background noise.'),
          const SizedBox(height: 12),
          TextField(
              controller: nameCtl,
              decoration: const InputDecoration(
                  labelText: 'Voice name', border: OutlineInputBorder())),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
                child: FilledButton.icon(
                    onPressed: toggleRecord,
                    icon: Icon(recording ? Icons.stop : Icons.mic),
                    label: Text(recording ? 'Stop' : 'Record'))),
            const SizedBox(width: 12),
            Expanded(
                child: OutlinedButton.icon(
                    onPressed: pick,
                    icon: const Icon(Icons.upload_file),
                    label: const Text('Pick file'))),
          ]),
          if (samplePath != null)
            Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text('Sample: ${samplePath!.split(RegExp(r'[\\/]')).last}')),
          CheckboxListTile(
            value: consent,
            onChanged: (v) => setState(() => consent = v ?? false),
            controlAffinity: ListTileControlAffinity.leading,
            contentPadding: EdgeInsets.zero,
            title: const Text(
                'I own this voice or have the speaker\'s permission to clone it.'),
          ),
          FilledButton(
              onPressed: (consent && !busy) ? upload : null,
              child: Text(busy ? 'Uploading...' : 'Create voice')),
          const Divider(height: 32),
          const Text('Saved voices', style: TextStyle(fontSize: 18)),
          for (final v in widget.home.voices)
            ListTile(
              title: Text(v.name),
              trailing: IconButton(
                icon: const Icon(Icons.delete_outline),
                onPressed: () async {
                  await http.delete(widget.home.url('/voices/${v.id}'),
                      headers: widget.home.headers);
                  widget.home.refresh();
                },
              ),
            ),
        ],
      );
}

class SpeakTab extends StatefulWidget {
  final _HomeState home;
  const SpeakTab({super.key, required this.home});
  @override
  State<SpeakTab> createState() => _SpeakTabState();
}

class _SpeakTabState extends State<SpeakTab> {
  static const langs = {
    'English': 'en', 'Spanish': 'es', 'French': 'fr', 'German': 'de',
    'Italian': 'it', 'Portuguese': 'pt', 'Polish': 'pl', 'Turkish': 'tr',
    'Russian': 'ru', 'Dutch': 'nl', 'Czech': 'cs', 'Arabic': 'ar',
    'Chinese': 'zh-cn', 'Japanese': 'ja', 'Hungarian': 'hu', 'Korean': 'ko',
  };
  final textCtl = TextEditingController();
  final player = AudioPlayer();
  String? voiceId;
  String lang = 'en';
  String? outPath;
  bool busy = false;

  Future<void> generate() async {
    final h = widget.home;
    if (voiceId == null || textCtl.text.trim().isEmpty) {
      h.toast('Choose a voice and enter text');
      return;
    }
    setState(() => busy = true);
    try {
      final res = await http.post(h.url('/speak'),
          headers: {...h.headers, 'Content-Type': 'application/json'},
          body: jsonEncode(
              {'voice_id': voiceId, 'text': textCtl.text, 'language': lang}));
      if (res.statusCode == 200) {
        final dir = await getApplicationDocumentsDirectory();
        final f = File(
            '${dir.path}/speech_${DateTime.now().millisecondsSinceEpoch}.wav');
        await f.writeAsBytes(res.bodyBytes);
        setState(() => outPath = f.path);
        await player.play(DeviceFileSource(f.path));
      } else {
        h.toast(jsonDecode(res.body)['detail']?.toString() ?? 'Failed');
      }
    } catch (e) {
      h.toast('Generation failed: $e');
    }
    setState(() => busy = false);
  }

  Future<void> save() async {
    if (outPath == null) return;
    if (Platform.isAndroid || Platform.isIOS) {
      await Share.shareXFiles([XFile(outPath!)]);
    } else {
      final dest = await FilePicker.platform.saveFile(
          fileName: 'speech.wav', type: FileType.audio);
      if (dest != null) {
        await File(outPath!).copy(dest);
        widget.home.toast('Saved');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final vs = widget.home.voices;
    return ListView(padding: const EdgeInsets.all(16), children: [
      DropdownButtonFormField<String>(
        value: vs.any((v) => v.id == voiceId) ? voiceId : null,
        decoration: const InputDecoration(
            labelText: 'Voice', border: OutlineInputBorder()),
        items: [
          for (final v in vs) DropdownMenuItem(value: v.id, child: Text(v.name))
        ],
        onChanged: (v) => setState(() => voiceId = v),
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        value: lang,
        decoration: const InputDecoration(
            labelText: 'Language', border: OutlineInputBorder()),
        items: [
          for (final e in langs.entries)
            DropdownMenuItem(value: e.value, child: Text(e.key))
        ],
        onChanged: (v) => setState(() => lang = v ?? 'en'),
      ),
      const SizedBox(height: 12),
      TextField(
        controller: textCtl,
        maxLines: 6,
        maxLength: 2000,
        decoration: const InputDecoration(
            labelText: 'Text to speak', border: OutlineInputBorder()),
      ),
      FilledButton.icon(
          onPressed: busy ? null : generate,
          icon: const Icon(Icons.play_arrow),
          label: Text(busy ? 'Generating...' : 'Generate audio')),
      if (outPath != null) ...[
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
              child: OutlinedButton.icon(
                  onPressed: () => player.play(DeviceFileSource(outPath!)),
                  icon: const Icon(Icons.replay),
                  label: const Text('Play'))),
          const SizedBox(width: 12),
          Expanded(
              child: OutlinedButton.icon(
                  onPressed: save,
                  icon: const Icon(Icons.download),
                  label: const Text('Save / Share'))),
        ]),
      ],
    ]);
  }
}

class SettingsTab extends StatefulWidget {
  final _HomeState home;
  const SettingsTab({super.key, required this.home});
  @override
  State<SettingsTab> createState() => _SettingsTabState();
}

class _SettingsTabState extends State<SettingsTab> {
  late final s = TextEditingController(text: widget.home.server);
  late final k = TextEditingController(text: widget.home.apiKey);

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
              controller: s,
              decoration: const InputDecoration(
                  labelText: 'Server URL (e.g. http://192.168.1.20:8000)',
                  border: OutlineInputBorder())),
          const SizedBox(height: 12),
          TextField(
              controller: k,
              obscureText: true,
              decoration: const InputDecoration(
                  labelText: 'API key (optional)',
                  border: OutlineInputBorder())),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: () async {
              final p = await SharedPreferences.getInstance();
              await p.setString('server', s.text.trim());
              await p.setString('key', k.text.trim());
              widget.home.server = s.text.trim();
              widget.home.apiKey = k.text.trim();
              await widget.home.refresh();
              widget.home.toast('Saved');
            },
            child: const Text('Save & connect'),
          ),
        ],
      );
}
