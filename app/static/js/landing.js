// ランディングページ（サービス版で未ログインのときに出す。ログアウトしたときもここに戻る）
import { el, typeChip } from './ui.js';

const CONTACT = 'https://forms.gle/BZJUwgC3okBH2XrW9';

// ---- 画面のイメージ（実際の画面を簡略化したもの） ----
const chip = (t) => typeChip(t, '', true);
const mon = (name, ...types) => el('span', { class: 'lp-mon' }, name, el('span', { class: 'tchips' }, ...types.map(chip)));
const src = (cls, text) => el('span', { class: `src src-${cls}` }, text);
const bar = (min, max) => el('div', { class: 'm-bar' }, el('span', { class: 'max', style: `width:${max}%` }), el('span', { class: 'min', style: `width:${min}%` }));
const phone = (title, ...body) => el('div', { class: 'lp-phone', 'aria-hidden': 'true' },
  el('div', { class: 'lp-phone-bar' }, el('span', {}, title)), el('div', { class: 'lp-phone-body' }, ...body));

// 逆算: 記録から相手の型が絞れていく画面
const inferMock = () => phone('対戦',
  el('div', { class: 'lp-mini-h' }, '相手の型', ' ', src('inferred', '逆算')),
  el('div', { class: 'lp-mini-card' }, mon('カイリュー', 'Dragon', 'Flying'),
    el('dl', {}, el('dt', {}, '性格'), el('dd', {}, 'いじっぱり', src('inferred', '逆算')),
      el('dt', {}, '持ち物'), el('dd', {}, 'こだわりハチマキ', src('inferred', '逆算')),
      el('dt', {}, '能力P'), el('dd', {}, 'A32 S20〜32', src('inferred', '逆算')),
      el('dt', {}, '技'), el('dd', {}, 'しんそく', src('confirmed', '確定')))),
  el('div', { class: 'lp-mini-rec' }, el('b', {}, '記録'), ' しんそく → ガブリアス 185→97（88ダメージ）'));

// ダメ計: 技ごとのダメージと確定数
const calcMock = () => phone('ダメ計',
  el('div', { class: 'lp-mini-h' }, 'ガブリアス → カイリュー'),
  // 実際の計算値（ガブリアス ようき A32 いのちのたま → カイリュー いじっぱり H32 マルチスケイル）
  ...[['ドラゴンクロー', 'Dragon', 47.5, 55.6, '乱数2発'], ['ストーンエッジ', 'Rock', 39.4, 46.5, '確定3発'], ['じしん', 'Ground', 0, 0, '効果なし']]
    .map(([mv, t, lo, hi, ko]) => el('div', { class: 'lp-mini-move' + (hi ? '' : ' immune') },
      el('div', { class: 'lp-mini-mv' }, typeChip(t, mv, false), el('span', { class: 'lp-ko' }, ko)),
      hi ? bar(lo, hi) : '', hi ? el('div', { class: 'lp-pct' }, `${lo}〜${hi}%`) : '')));

// 記録: 被ダメを入れると、型の候補が絞られる
const recordMock = () => phone('対戦',
  el('div', { class: 'lp-seg' }, el('span', { class: 'on' }, '被ダメ'), el('span', {}, '与ダメ'), el('span', {}, '判明')),
  el('div', { class: 'lp-form' },
    el('label', {}, '攻撃した相手', el('b', {}, 'カイリュー')), el('label', {}, '技', el('b', {}, 'しんそく')),
    el('label', {}, '受けた自分', el('b', {}, 'ガブリアス')), el('label', {}, '受けた後のHP', el('b', {}, '97 / 185'))),
  el('div', { class: 'lp-add' }, '追加'),
  el('div', { class: 'lp-mini-rec' }, el('b', {}, '反映'), ' 相手の性格・持ち物・Aの能力ポイントの候補を絞り込み、ダメ計と素早さに反映'));

// 選出予想
const selectMock = () => phone('選出',
  el('div', { class: 'lp-mini-h' }, 'おすすめの選出'),
  el('div', { class: 'lp-mini-picks' }, mon('ガブリアス', 'Dragon', 'Ground'), mon('アーマーガア', 'Flying', 'Steel'), mon('ウォッシュロトム', 'Electric', 'Water')),
  el('div', { class: 'lp-mini-h' }, '相手ごとの対応'),
  ...[['カイリュー', ['Dragon', 'Flying'], 'ガブリアス'], ['サーフゴー', ['Steel', 'Ghost'], 'ガブリアス'], ['ドヒドイデ', ['Poison', 'Water'], 'ウォッシュロトム']]
    .map(([o, ts, me]) => el('div', { class: 'lp-mini-ans' }, mon(o, ...ts), el('span', { class: 'lp-arrow' }, '→'), el('b', {}, me))));

// 取り込み: スクショ2枚から6体
const importMock = () => phone('パーティ',
  el('div', { class: 'lp-shots' }, el('div', { class: 'lp-shot' }, '能力'), el('div', { class: 'lp-shot' }, 'ステータス')),
  el('div', { class: 'lp-arrow-down' }, '↓ 6体をまとめて読み取り'),
  ...[['ガブリアス', 'いじっぱり', 'H32 B22 D7 S5'], ['ゲンガー', 'おくびょう', 'H14 C20 S32'], ['アーマーガア', 'わんぱく', 'H32 B25 D7 S2']]
    .map(([n, nat, sp]) => el('div', { class: 'lp-mini-row' }, el('b', {}, n), el('span', {}, nat), el('small', {}, sp))));

// ---- ページ ----
export function landingView(login) {
  const cta = (label = 'Googleで無料ではじめる') => el('button', { class: 'btn primary big lp-cta', onclick: login }, label);
  const steps = [
    ['Step 1', 'パーティを登録する', 'ゲームの「パーティ確認」画面のスクショ2枚から、6体の型をまとめて取り込めます。手で入力するときも、よく使われている型で空欄を埋められます。', importMock],
    ['Step 2', '見せ合いで選出を予想する', '相手の6体を入れると、相手が出してきそうな3体と、自分のおすすめの選出、対面ごとの有利・不利がすぐに出ます。', selectMock],
    ['Step 3', '対戦中は記録して逆算する', '受けたダメージ・与えたダメージ・見えた持ち物を記録するたびに、相手の性格・持ち物・能力ポイントが絞り込まれ、ダメ計と素早さに反映されます。', recordMock],
  ];
  const features = [
    ['逆', '逆ダメ計', 'ダメージの記録から相手の型を逆算。確定した情報と、逆算・採用率からの推定を分けて表示します。'],
    ['計', 'ダメ計', 'ランク・天候・フィールド・壁・状態異常・メガシンカまで。相手の技はよく使われるものをまとめて表示します。'],
    ['速', '素早さ比較', '相手の最速・準速・スカーフと自分の実数値を1本に並べて、ランク変化後の順番も確かめられます。'],
    ['⇄', '行き来がすぐ', '対戦とダメ計を切り替えても待たされない作り。スマホでもPCでも、対戦の横に置いて使えます。'],
  ];
  return el('div', { class: 'lp' },
    // ヒーロー
    el('section', { class: 'lp-hero' },
      el('div', { class: 'lp-wrap lp-hero-in' },
        el('div', { class: 'lp-hero-text' },
          el('p', { class: 'lp-kicker' }, 'ポケモンチャンピオンズ シングル対戦のノート'),
          el('h1', {}, '記録するほど、', el('br'), '相手の型が', el('br'), '見えてくる。'),
          el('p', { class: 'lp-sub' }, '受けたダメージ・与えたダメージを記録するだけで、相手の性格・持ち物・能力ポイントを逆算。選出予想からダメ計まで、対戦の横に置いて使えます。'),
          cta(),
          el('p', { class: 'lp-note' }, '登録は Google アカウントだけ。保存する個人情報はメールアドレスのみです。')),
        el('div', { class: 'lp-hero-art' }, calcMock(), inferMock()))),
    // とは
    el('section', { class: 'lp-about' },
      el('div', { class: 'lp-wrap' },
        el('h2', { class: 'lp-h2' }, 'ギャクダメノートとは？'),
        el('p', {}, '「この火力、ハチマキ？」「どれだけ耐久に振ってる？」――対戦中に迷ったことはありませんか。'),
        el('p', {}, 'ギャクダメノートは、対戦で見えたダメージから相手の型を逆算する「逆ダメ計」を中心に、選出予想・ダメ計・素早さ比較をひとつにまとめたサービスです。'))),
    // 使い方
    el('section', { class: 'lp-flow' },
      el('div', { class: 'lp-wrap' },
        el('h2', { class: 'lp-h2' }, '使い方'),
        ...steps.map(([n, title, text, mock], i) => el('div', { class: 'lp-step' + (i % 2 ? ' rev' : '') },
          el('div', { class: 'lp-step-text' }, el('span', { class: 'lp-step-n' }, n), el('h3', {}, title), el('p', {}, text)),
          el('div', { class: 'lp-step-art' }, mock()))))),
    // できること
    el('section', { class: 'lp-features' },
      el('div', { class: 'lp-wrap' },
        el('h2', { class: 'lp-h2' }, 'できること'),
        el('div', { class: 'lp-feature-grid' }, ...features.map(([icon, title, text]) =>
          el('div', { class: 'lp-feature' }, el('span', { class: 'lp-feature-icon' }, icon), el('h3', {}, title), el('p', {}, text)))))),
    // 最後のCTA
    el('section', { class: 'lp-final' },
      el('div', { class: 'lp-wrap' },
        el('h2', {}, '次の対戦から、使ってみよう。'),
        el('p', {}, '無料ではじめられます。パーティと対戦の記録は、あなたにしか見えません。'),
        cta())),
    el('footer', { class: 'lp-footer' },
      el('div', { class: 'lp-wrap' },
        el('p', {}, el('a', { href: '/terms' }, '利用規約'), '・', el('a', { href: '/privacy' }, 'プライバシーポリシー'), '・',
          el('a', { href: CONTACT, target: '_blank', rel: 'noopener' }, 'お問い合わせ')),
        el('p', { class: 'lp-disclaimer' }, '個人が運営する非公式のファンツールです。株式会社ポケモン・任天堂株式会社・株式会社クリーチャーズ・株式会社ゲームフリークとは関係ありません。ポケモンの名称等の権利は各権利者に帰属します。'),
        el('p', { class: 'lp-copy' }, '© ギャクダメノート（Gyakudame Note）'))));
}
