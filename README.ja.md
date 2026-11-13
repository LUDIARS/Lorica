# Lorica

[English](README.md)

C++ サービス向けに組み合わせて使うセキュリティライブラリ群です。プロジェクトコード: **Lr**。
Lorica は「鎧」を意味します。各部品は防御の層を足すものであり、完全なメモリ安全性を与えるものではありません。

部品 (特記がなければ C++17、すべて C++23 でもテスト済み。CMake 3.24 以上):

| 部品 | 契約 |
| --- | --- |
| `Lorica::boundary` | 検査付きサイズ演算、範囲付きバイトビュー、リクエスト単位の累積予算 |
| `Lorica::boundary` (C++20 ヘッダ) | 任意の整数型の検査付き演算、範囲付き文字列コピー/追記/整形、バイト順に依存しないバイト読み取り ([検査付き API](spec/feature/checked-apis.md)) |
| `Lorica::protection` | OS の専用読み取り専用領域: 1 マッピングに不変の算術型/列挙型の値 1 つ (`sealed_value`)、または多数の値・構造体・表を 1 つの封印マッピングに (`sealed_pack`) |
| `Lorica::contracts` | C++26 契約のエミュレーション (`LORICA_PRE` / `LORICA_POST` / `LORICA_CONTRACT_ASSERT`)、4 つの評価セマンティクス、差し替え可能な違反ハンドラ |
| `lorica_harden_target` | ターゲット単位のベースライン堅牢化。任意で厳格な `EXTENDED` プロファイルと、configure 時の対応可否の問い合わせ |
| `lorica_deprecate_unsafe_apis` | ターゲットの C++ ソースでの `strcpy`/`strcat`/`sprintf`/`vsprintf`/`wcscpy`/`wcscat` の使用をコンパイルエラーにする。非推奨警告はすべてエラーになる。[限界](spec/feature/security-contracts.md#SPEC-LR-UNSAFE-API) |
| `LoricaInject.cmake` | 明示したターゲット許可リストに対する、外部からの CMake 注入 |
| `lorica_use_iso_cxx23` | MSVC 19.52 以上で `cxx_std_23` を CMake 既定の `/std:c++latest` ではなく ISO の `/std:c++23` にする ([対応標準](spec/feature/security-contracts.md#SPEC-LR-CXX23)) |
| `tools/verify_binary.py` | PE/ELF 実行ファイルの選択したメタデータを検査する。バイナリは実行しない |
| `tools/lorica_analyze.py` | C/C++ のテキストから読むアサーション型のソースゲート: `complexity` (循環的複雑度、認知的複雑度、ネスト、引数、NLOC)、`shared-state` (データごとのロックセット、アトミックとそのメモリ順序)、`constexpr` (ツリーのコピー上で GCC/Clang に指定子を試させる)。しきい値とベースラインを持ち、違反で exit 1。解析・解決できなかったものも報告する ([限界](spec/feature/source-analysis.md#SPEC-LR-ANALYZE)) |

## 使い方

```cmake
find_package(Lorica 0.1 CONFIG REQUIRED)
target_link_libraries(my_service PRIVATE Lorica::boundary)
lorica_harden_target(my_service)
```

`add_subdirectory` でこのリポジトリを追加しても使えます (自分のインストールに Lorica のヘッダと
パッケージファイルが入らないよう `EXCLUDE_FROM_ALL` を付けてください)。ネットワーク取得、パッケージ
マネージャ、インストール時スクリプト、サードパーティのランタイムはいずれも不要です。
`COMPONENTS protection` や `contracts` にはコンパイル部品が必要です。インストールは CMake で行います。
ビルド種別を指定しないと、配布するライブラリが最適化なし・FORTIFY なしでビルドされます:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
cmake --install build --config Release --prefix /your/prefix
```

既存の CMake プロジェクトには、ソースを編集せずにビルド保護を注入できます:

```sh
cmake -S /service/source -B /service/build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=/path/to/Lorica/cmake/LoricaInject.cmake \
  '-DLORICA_TARGETS=my_service;my_parser' \
  -DLORICA_PROFILE=extended -DLORICA_DEPRECATE_UNSAFE_APIS=ON   # 任意
```

列挙するターゲットはすべて存在し、ローカルでコンパイルされるものでなければなりません。単一構成の
ジェネレータにはビルド種別が必要です。空のビルド種別では FORTIFY が付かず、EXTENDED もそれを拒否しません。
境界検査は呼び出し側での採用が引き続き必要です。DLL を読み込んでも任意の C++ に後付けはできません。
注入フックはトップレベルの configure であることを前提とし、依存グラフをたどるものではありません。
保護が必要なソースビルドのライブラリは、それぞれ明示的に列挙してください。

```cpp
#include <lorica/checked_size.hpp>
#include <lorica/input_budget.hpp>

lorica::input_budget budget({1024 * 1024, 4096, 128, 32});
const auto bytes = lorica::checked_multiply(element_count, element_size);
if (!bytes || !budget.consume(*bytes, element_count, 1)) {
    return reject_request(); // 想定内の不正入力は拒否する。サービスは中断しない。
}
// 検査に成功してから確保・処理する。この例は概略です。
```

C++20 では、検査付き API が典型的なパーサの残りの部分を受け持ちます:

```cpp
#include <lorica/bounded_text.hpp>
#include <lorica/byte_reader.hpp>
#include <lorica/checked_integer.hpp>
#include <cstdint>

lorica::byte_reader in(packet);                   // std::span<const std::byte>
const auto count = in.read_big_endian<std::uint32_t>();
const auto name = in.read_prefixed<std::uint16_t, std::endian::big>();
const auto total = count ? lorica::checked_multiply(*count, record_size) : std::nullopt; // record_size は std::uint32_t: 2 つの被演算子は同じ型
char label[32];
if (!name || !total || !lorica::format_into(label, "{} records", *count)) return reject_request();
```

Linux のベースラインは、libstdc++ のアサーションまたは libc++ の FAST、最適化構成での FORTIFY、
対応するスタッククラッシュ保護と制御フロー保護のフラグを要求します。
`lorica_harden_target(my_service EXTENDED)` はそのターゲットを libc++ EXTENSIVE または libstdc++
アサーションに引き上げ、Linux プロファイルのスタック保護と分岐保護、ゼロ初期化、最適化構成での
実効 FORTIFY レベル 3 を必須にします。Windows ではネイティブ MSVC 19.44 以上 x64 の STL 堅牢化と
CET 互換リンクを必須にします。[プロファイル表](spec/feature/security-contracts.md#SPEC-LR-EXTENDED)を参照してください。

`lorica_deprecate_unsafe_apis(my_service)` は、これとは別に
[危険な API の拒否](spec/feature/security-contracts.md#SPEC-LR-UNSAFE-API)を有効にします。
`format_into` には `__cpp_lib_format` を持つ標準ライブラリが必要です。

## 対応標準とツールチェーン

| 標準 | 状態 |
| --- | --- |
| C++17 | `checked_size`、`byte_view`、`input_budget`、`Lorica::protection`、`Lorica::contracts` の最小要件 |
| C++20 | `checked_integer`、`bounded_text`、`byte_reader` の最小要件 |
| C++23 | 正式対応。すべての C++ 部品のテストを C++23 でも実行する |

最小要件より古い標準でヘッダを使うと `#error` で止まります。C++23 とは ISO C++23 のことで、草案モード
ではありません。CMake は MSVC で `cxx_std_23` を `/std:c++latest` (C++26 草案の機能も有効になる) に
写すため、Lorica は MSVC 19.52 以上 (Visual Studio 2026 18.12 以上) でこれを `/std:c++23` に切り替えます。
`find_package(Lorica)` は呼び出したディレクトリとその配下に、`LoricaInject.cmake` はビルド全体に、
Lorica 自身のビルドは自分のツリーだけに適用します。それより古い MSVC には ISO C++23 のスイッチが無いため、
C++23 のテストは `/std:c++latest` で実行され、`lorica.standard.cxx23` は "Not Run" と報告されます。
Linux の GCC 11 以上/Clang 17 以上は CMake の `-std=c++23` を使います。
[SPEC-LR-CXX23](spec/feature/security-contracts.md#SPEC-LR-CXX23) を参照してください。

## 保護の限界

`byte_view` は所有しません。呼び出し側は、生存中の連続オブジェクトの実際のサイズを渡し、並行して
変更されないよう保持しなければなりません。添字はその申告サイズに対して検査され、ポインタが有効かは
検査しません。解放後使用、二重解放、無効なポインタ、型の取り違え、生ポインタ経由の迂回は検出しません。
メモリの確保・解放は行いません。予算はリクエストごとのもので、スレッドセーフではありません。
課金は処理より先に行い、展開後の出力と入れ子の確保も含め、リクエストを通じて同じ予算を使う必要が
あります。深さは正直に申告されなければなりません。
`checked_size.hpp` の `size_t` 版の関数は言語規則で変換された被演算子を受け取るため、負の値や
より広い型の値は検出されません。`checked_integer.hpp` の `narrow` か、`-Wconversion -Wsign-conversion`
を使ってください。タイムアウト、並行数の制限、認証は引き続きサービス側の責務です。

堅牢化は Windows の MSVC 互換ツールチェーンと Linux の GCC/Clang に対応します。契約ランタイムは
堅牢化されてビルドされるため、それ以外の環境ではヘッダだけの部品を使うよう
`-DLORICA_BUILD_CONTRACTS=OFF` (と `LORICA_BUILD_PROTECTION=OFF`) で configure してください。
ビルド済みの依存物は保護せず、すべてのオブジェクトに計装があることも証明せず、侵害されたプロセスを
信頼できるものにもしません。後から矛盾するビルドフラグを与えると保護が弱まることがあるため、実際の
コマンドと成果物を確認してください。汎用のメモリバリア、セキュアアロケータ、暗号、認証はここでは
実装していません。`std::atomic_thread_fence` (スレッド間の順序付け) はこれらの保護と無関係です。

C++23 対応はビルド時の性質であり、実行時の検査やセキュリティ保証を追加するものではありません。

## 契約 (C++26 のエミュレーション)

契約は、アサーションと同じく正しいプログラムで成り立つことを述べるもので、役割 (事前条件、事後条件、
アサーション) と、ビルドで選ぶ評価セマンティクスを持ちます。`Lorica::contracts` をリンクし、実行ファイルと
そのすべてのプラグインに対して、1 つのランタイム DLL/共有オブジェクトを配置してください。

関数本体の中で (`<lorica/contracts.hpp>`):

```cpp
int element(std::span<const int> values, std::size_t index) {
    LORICA_PRE(index < values.size());
    return values[index];
}
constexpr int square(int v) { return LORICA_POST_RETURN(v * v, r, r >= 0); }
```

各マクロは条件を 1 つだけ取ります。述語のテキストがメッセージになるため、`LORICA_PRE(ok, "message")`
はコンパイルできません。

既存のコードを編集せず、外から被せる形で
(`<lorica/contract_overlay.hpp>`、[オーバーレイ](spec/feature/contracts.md#SPEC-LR-CONTRACT-OVERLAY)):

```cpp
int reserve(int in_stock, int requested);                     // 既存のまま変更しない

constexpr auto checked_reserve = LORICA_CONTRACT(reserve)
    .pre([](int in_stock, int requested) { return requested >= 0 && requested <= in_stock; },
         "request is covered by the stock")
    .post([](int left, int in_stock, int requested) { return left == in_stock - requested; },
          "what is left is the stock less the request");      // 結果が先頭に来る

const int left = checked_reserve(in_stock, requested);        // 同じ呼び出しを検査付きで
```

同じ条件がその関数のテストになります。`test` は違反を処理する代わりに報告し、事前条件が拒否する
呼び出しは決して行いません:

```cpp
using lorica::contracts::test_status;
require(static_cast<bool>(checked_reserve.test(10, 3)));
const auto refused = checked_reserve.test(10, 11);            // reserve は呼ばれない
require(refused.status == test_status::precondition_failed);
require(std::string_view(refused.condition) == "request is covered by the stock");
```

セマンティクスは、ソースを編集せずにビルドからターゲットごとに選びます:
`lorica_set_contract_semantic(my_service enforce)` (既定。ほかに `observe`、`quick_enforce`、検査を取り除いて
素の呼び出しだけを残す `ignore`)。既存プロジェクトでは `LoricaInject.cmake` で `LORICA_TARGETS` と並べて
`-DLORICA_CONTRACT_SEMANTIC=ignore` を渡すと、プロジェクト自身が選んだセマンティクスを置き換えます。
契約を含むインライン/テンプレートのコードを共有するターゲットには同じセマンティクスを与えてください
(すべてを `LORICA_TARGETS` に列挙する)。そうしないと、どの検査が実行されるかは未規定です (P2900 の
混在モード)。契約はバグを捕まえるためのもので、入力検証ではありません。入力検証は `ignore` で消えては
いけません。`examples/contracts` は 1 つの契約を、正しい実装と欠陥のある実装の両方にテスト表として
適用します。[契約の仕様](spec/feature/contracts.md)を参照してください。

## 書き込み保護された変数

`Lorica::protection` をリンクし、`<lorica/sealed_value.hpp>` をインクルードします:

```cpp
const lorica::sealed_value<unsigned> maximum_requests(128);
const unsigned limit = maximum_requests.load(); // 保護されない値のコピー。
```

元のバイト列は、実行権限なしで要求した OS の専用マッピングに置かれ、構築が戻る前に読み取り専用に
封印されます。セッターや変更可能なポインタはありません。対応するのは算術型と列挙型の値だけです。
OS の確保・保護のエラーは例外を投げ、書き込み可能なままの代替経路はありません。実装は Windows と
Linux に対応しますが、各プラットフォームでのテスト実行は別途確認が必要です。
`LORICA_BUILD_PROTECTION=OFF` は `Lorica::protection` を省き、そのヘッダもインストールしません。

これはプロセスの生存期間を通じた少数の設定値に向いており、すべての変数向けではありません。値ごとに
専用のマッピングと少なくとも 1 ページの常駐ページを使い、Linux ではプロセスあたりのマッピング数が
`vm.max_map_count` に制限されます。多数の値には sealed pack を使ってください。値は `main` の中で
try/catch のもとで構築してください。名前空間スコープでは、構築に失敗すると `main` の前に終了します。
通常の禁止された書き込みはプロセスをフォールトさせます。プロセス自身が `madvise` で値をゼロにすること、
`/proc/self/mem` や `ptrace` 経由で書き込むこと、自分で `mprotect`/`munmap`/`mmap(MAP_FIXED)` を使うことは
防がず、コピーや所有者オブジェクトも保護しません。秘密の秘匿、メモリの安全な消去、無関係な確保領域の
保護も行いません。所有者は読み取りより長く生存し、並行する読み手へ安全に公開されなければなりません。
限界と推奨する開発ツール (ASan、UBSan、TSan、ファジング) は[保護の契約](spec/feature/sealed-values.md)を
参照してください。

## sealed pack

構造体、表、少数を超える値は、`pack_builder` に積んでから 1 つの読み取り専用マッピングに封印します
(リンク先は同じ、`<lorica/sealed_pack.hpp>`):

```cpp
lorica::pack_builder builder(1024);              // 容量は信頼できる設定から
const auto limits = builder.add(service_limits{512, 1u << 20, 30, true});
const auto table = builder.add_array(hex.data(), hex.size());
if (!limits || !table) return false;             // 入りきらない: 例外ではなく値で返る
const lorica::sealed_pack pack(std::move(builder)); // これが戻った時点で読み取り専用
const service_limits copy = pack.load(*limits);
const std::optional<std::int8_t> digit = pack.at(*table, index); // 範囲外なら空
```

読み取りはコピーを返します。スロットが pack の外にある読み取りは終了させます。これは読み取りの範囲を
制限するもので、それが誰のスロットかは判別しません。封印は浅く、メンバが指す先のメモリは保護されません。
pack が構築されるまで値は保護されません。`examples/packing` は封印した設定を読み戻し、値ごとに
`sealed_value` を 1 つ使う場合と pack を手元のホストで比較測定します。数値は約束しません。
[pack の契約](spec/feature/sealed-packs.md)を参照してください。

## ソース解析

`tools/lorica_analyze.py` は C と C++ のソースをテキストとして読み (Python 3 標準ライブラリのみ。
コンパイラ不要で、何も編集・実行しない)、アサーションのように失敗します:

```sh
python3 tools/lorica_analyze.py complexity src include --max-cognitive 15 --max-cyclomatic 10
python3 tools/lorica_analyze.py complexity src --write-baseline analysis-baseline.json   # 最初に 1 回採用
python3 tools/lorica_analyze.py complexity src --strict --max-cognitive 15 --baseline analysis-baseline.json
```

exit 0: 範囲内。1: しきい値を超えた関数、またはベースラインより悪化した関数がある。2: 使い方の誤り、
読めない入力、または `--strict` 指定時の解析できなかった領域。どの報告も、解析した関数、解析できなかった
領域、解析しなかった行を示します。CTest のゲートとしては:

```cmake
add_test(NAME myapp.complexity COMMAND ${Python3_EXECUTABLE}
    ${LORICA_SOURCE_DIR}/tools/lorica_analyze.py complexity --strict --max-cognitive 15
    --baseline ${CMAKE_CURRENT_SOURCE_DIR}/analysis-baseline.json ${CMAKE_CURRENT_SOURCE_DIR}/src)
```

`shared-state` は同じソースから共有データを読みます。メモリバリア (`std::atomic_thread_fence`) は
非アトミックなオブジェクトのデータ競合を決して直しません。共有される素のデータには `std::atomic` か、
すべてのアクセスで同じロックが必要です。このツールはデータごとに、アクセス時に保持しているロックを
列挙し、上限を与えた種類の所見があれば失敗します:

```sh
python3 tools/lorica_analyze.py shared-state src include --all     # データごとの表
python3 tools/lorica_analyze.py shared-state src include --strict \
    --max-inconsistent-locking 0 --max-unsynchronized 0 --max-relaxed-publication 0 --max-invalid-order 0
```

`lock:<names>` は解析したファイルの中で一貫していることを意味し、競合がないことの証明ではありません。
証拠には ThreadSanitizer を使ってください。解決できなかったコードは `unknown` と報告され、安全とは
報告されません。Lorica 自身に対しては、アトミック 1 つ (`installed_handler`)、`thread_local` 1 つ、
共有ストリーム 1 つを報告します ([自己報告](spec/plan/2026-11-13-shared-state-report.md))。

`constexpr` はツリーの一時コピー上で (手元のファイルでは決して行わない) GCC または Clang に `constexpr`
指定子を試させ、コンパイラと標準ごとに `rejected`、`accepted` (コンパイラが許容する: 必要条件にすぎず
未検証)、`witnessed` (利用者が与えた `static_assert` の証拠が変更ありでコンパイルでき、変更なしで失敗する:
唯一の検証済み状態) を報告します。コンパイラが無ければ、constexpr 宣言されていない関数と、一部を除外した
理由だけを列挙します。MSVC には対応しません。

```sh
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
python3 tools/lorica_analyze.py constexpr include src --compile-commands build/compile_commands.json \
    --std 17 --std 20 --witnesses constexpr-witnesses.json --max-witnessed 0
```

`--max-witnessed 0` は、変換可能と証明された関数が constexpr 宣言されていない間は失敗します。
`--emit-patch FILE` はレビュー用の差分を書き出します (適用はしません)。

[examples/analysis](examples/analysis/README.md) と [SPEC-LR-ANALYZE](spec/feature/source-analysis.md) の
限界を参照してください。

[セキュリティ契約](spec/feature/security-contracts.md)、[検証](spec/test/verification.md)、
[依存関係のレビュー](DEPENDENCIES.md)も参照してください (いずれも英語)。

## 状態

初期実装であり、本番向けセキュリティ認証ではありません。既存サービスの移行はまだ行っていません。
リリースの公開とレビューは別の手順です。
