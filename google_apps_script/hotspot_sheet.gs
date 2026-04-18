const DOMESTIC_SITE_FILTER =
  '(site:sports.sina.com.cn OR site:sports.qq.com OR site:sports.163.com OR ' +
  'site:sports.cctv.com OR site:sports.people.com.cn OR site:news.sports.cn OR ' +
  'site:sports.sohu.com)';

const HOTSPOT_CONFIG = {
  targetSheetName: '工作表1',
  topN: 20,
  minScore: 5.0,
  dailyHour: 8,
  querySpecs: [
    {
      name: 'domestic_league_cn',
      query: '(CBA OR WCBA OR 中国女篮 OR 中国男篮 OR 中超 OR 国足 OR 足协杯) ' + DOMESTIC_SITE_FILTER + ' -site:fans.sports.qq.com when:1d',
      league: '',
      required_keywords: ['CBA', 'WCBA', '中国女篮', '中国男篮', '中超', '国足', '足协杯', '蓉城', '国安', '泰山', '海港'],
    },
    {
      name: 'national_team_cn',
      query: '(国乒 OR WTT OR 国羽 OR 羽毛球 OR 郑钦文 OR 张帅 OR 中国球员 OR 中国选手 OR 斯诺克) ' + DOMESTIC_SITE_FILTER + ' when:1d',
      league: '',
      required_keywords: ['国乒', 'WTT', '国羽', '羽毛球', '郑钦文', '张帅', '中国球员', '中国选手', '斯诺克', '太原站'],
    },
    {
      name: 'basketball_global_cn',
      query: '(NBA OR 附加赛 OR 季后赛) ' + DOMESTIC_SITE_FILTER + ' -site:fans.sports.qq.com when:1d',
      league: '',
      required_keywords: ['NBA', '附加赛', '季后赛', '勇士', '湖人', '太阳', '魔术', '黄蜂'],
    },
    {
      name: 'football_global_cn',
      query: '(欧冠 OR 英超 OR 西甲 OR 意甲 OR 德甲 OR 转会) ' + DOMESTIC_SITE_FILTER + ' -site:fans.sports.qq.com when:1d',
      league: '',
      required_keywords: ['欧冠', '英超', '西甲', '意甲', '德甲', '转会', '利物浦', '巴萨', '皇马', '拜仁'],
    },
    {
      name: 'hot_cn',
      query: '(绝杀 OR 逆转 OR 晋级 OR 出局 OR 无缘 OR 伤退 OR 复出 OR 官宣) ' + DOMESTIC_SITE_FILTER + ' -site:fans.sports.qq.com when:1d',
      league: '',
      required_keywords: ['绝杀', '逆转', '晋级', '出局', '无缘', '伤退', '复出', '官宣'],
    },
  ],
  sheetColumns: [
    ['run_date', '日期'],
    ['rank', '排名'],
    ['total_score', '总分'],
    ['topic_type', '热点分类'],
    ['storyline_tags', '剧情标签'],
    ['title', '标题'],
    ['summary_hint', '简要摘要'],
    ['source', '来源'],
    ['source_count', '来源数'],
    ['published_at', '发布时间'],
    ['latest_published_at', '最新发布时间'],
    ['league_tags', '项目标签'],
    ['keyword_hits', '关键词'],
    ['entity_tags', '主体标签'],
    ['why_hot', '上榜原因'],
    ['reference_url', '原文链接'],
  ],
};

const HOTSPOT_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135 Safari/537.36',
};

const HOTSPOT_STORYLINE_PATTERNS = {
  transfer: ['transfer', 'trade', 'sign', 'signing', 'contract', 'loan', '转会', '加盟', '签约', '续约', '离队', '官宣'],
  injury: ['injury', 'injured', 'ruled out', 'questionable', 'doubtful', 'returns', 'return', '伤病', '伤缺', '伤停', '伤退', '报销', '缺席', '复出', '回归'],
  controversy: ['ban', 'suspension', 'scandal', 'controversy', 'criticism', '争议', '禁赛', '处罚', '罚单', '冲突', '质疑', '回应'],
  lineup: ['preview', 'lineup', 'lineups', 'kickoff', '赛前', '前瞻', '对阵', '迎战', '首发', '名单', '抽签', '分档', '名单公布', '今晚', '明日', '出战'],
  result: ['beat', 'beats', 'defeat', 'defeats', 'win', 'wins', 'won', 'loss', 'eliminate', 'eliminated', 'comeback', 'clinch', 'final', 'semifinal', '战胜', '击败', '不敌', '险胜', '大胜', '战平', '力克', '破门', '建功', '救主', '逆转', '绝杀', '晋级', '淘汰', '出局', '无缘', '夺冠', '问鼎', '冠军', '收官'],
  star: ['scores', 'scored', 'double-double', 'hat-trick', 'record', 'milestone', 'mvp', '砍下', '轰下', '拿到', '三双', '双响', '帽子戏法', '纪录', '里程碑'],
  business: ['media rights', 'broadcast', 'sponsorship', 'revenue', 'ownership', '赞助', '版权', '转播', '收购', '商业'],
};

const HOTSPOT_STORYLINE_LABELS = {
  transfer: '转会',
  injury: '伤病',
  controversy: '争议',
  lineup: '赛前',
  result: '赛果',
  star: '球星',
  business: '商业',
};

const HOTSPOT_TOPIC_LABELS = {
  sports_result: '赛果热点',
  sports_preview: '赛前热点',
  sports_star: '人物热点',
  sports_business: '商业热点',
  sports_low_value: '低优先级',
};

const HOTSPOT_SOURCE_WEIGHTS = {
  '央视网': 2.0,
  '央视体育': 2.0,
  '新华网': 1.9,
  '人民网': 1.8,
  '中国新闻网': 1.8,
  '腾讯网': 1.7,
  '腾讯体育': 1.8,
  '网易体育': 1.7,
  '搜狐体育': 1.6,
  '懂球帝': 1.6,
  '直播吧': 1.5,
  'reuters': 2.0,
  'associated press': 2.0,
  'ap': 2.0,
  'espn': 1.8,
  'the athletic': 1.8,
  'bbc sport': 1.7,
  'sky sports': 1.7,
  'nba.com': 1.7,
  'mlb.com': 1.7,
  'uefa': 1.7,
};

const HOTSPOT_KEYWORD_RULES = [
  {label: '季后赛', weight: 1.7, patterns: ['季后赛', 'playoff', 'playoffs']},
  {label: '附加赛', weight: 1.6, patterns: ['附加赛', 'play-in']},
  {label: '决赛', weight: 1.6, patterns: ['决赛', 'final']},
  {label: '半决赛', weight: 1.5, patterns: ['半决赛', 'semifinal']},
  {label: '夺冠', weight: 1.6, patterns: ['夺冠', '冠军', '问鼎', '获四冠']},
  {label: '绝杀', weight: 1.7, patterns: ['绝杀', 'buzzer-beater']},
  {label: '逆转', weight: 1.4, patterns: ['逆转', 'comeback']},
  {label: '晋级', weight: 1.8, patterns: ['晋级', 'advance', 'advanced']},
  {label: '淘汰', weight: 1.8, patterns: ['淘汰', 'eliminate', 'eliminated']},
  {label: '出局', weight: 1.6, patterns: ['出局', '无缘']},
  {label: '伤病', weight: 1.5, patterns: ['伤病', '伤缺', '伤退', 'injury']},
  {label: '复出', weight: 1.3, patterns: ['复出', '回归', 'returns', 'return']},
  {label: '转会', weight: 1.5, patterns: ['转会', '加盟', '签约', 'trade', 'transfer']},
  {label: '官宣', weight: 1.3, patterns: ['官宣', 'official']},
  {label: '争议', weight: 1.4, patterns: ['争议', '禁赛', '处罚', 'controversy', 'suspension']},
  {label: '纪录', weight: 1.2, patterns: ['纪录', 'record', '里程碑', 'milestone']},
  {label: '国足', weight: 1.3, patterns: ['国足']},
  {label: '中超', weight: 1.2, patterns: ['中超']},
  {label: '欧冠', weight: 1.5, patterns: ['欧冠', 'champions league']},
  {label: 'CBA', weight: 1.3, patterns: ['cba', 'cba季后赛']},
  {label: 'NBA', weight: 1.3, patterns: ['nba']},
  {label: '中国女篮', weight: 1.5, patterns: ['中国女篮', '女篮世界杯']},
  {label: '中国球员', weight: 1.4, patterns: ['中国球员', '中国选手']},
  {label: 'WTT', weight: 1.4, patterns: ['wtt', '太原站']},
  {label: '斯诺克', weight: 1.3, patterns: ['斯诺克']},
  {label: '入围', weight: 1.2, patterns: ['入围', '位列第二档', '名单公布', '选中']},
  {label: '国乒', weight: 1.4, patterns: ['国乒', 'wtt', '乒乓球']},
  {label: '国羽', weight: 1.3, patterns: ['国羽', '羽毛球']},
];

const HOTSPOT_KEYWORD_WEIGHTS = {};
HOTSPOT_KEYWORD_RULES.forEach((rule) => {
  HOTSPOT_KEYWORD_WEIGHTS[rule.label] = rule.weight;
});

const HOTSPOT_STRONG_EVENT_KEYWORDS = new Set([
  '季后赛', '附加赛', '决赛', '半决赛', '夺冠', '绝杀', '晋级', '淘汰', '出局',
  '伤病', '转会', '官宣', '欧冠', '中国女篮', '中国球员', 'WTT', '斯诺克',
]);

const HOTSPOT_LEAGUE_KEYWORDS = {
  'NBA': ['nba', '勇士', '湖人', '火箭', '凯尔特人', '雷霆', '太阳', '尼克斯', '掘金', '黄蜂', '魔术', '快船'],
  'CBA': ['cba', '辽宁男篮', '广东男篮', '北京男篮', '浙江男篮', '广厦', '上海久事', '北控', '山东'],
  'WCBA': ['wcba', '山西女篮', '四川女篮', '中国女篮'],
  '中超': ['中超', '泰山', '海港', '津门虎', '海牛', '成都蓉城', '北京国安', '韦世豪', '廖力生'],
  '中国女篮': ['中国女篮', '女篮世界杯'],
  '足球': ['足球', '中超', '英超', '西甲', '意甲', '德甲', '足协杯', '欧冠', '国足'],
  '国乒': ['国乒', 'wtt', '王楚钦', '孙颖莎', '樊振东', '黄友政', '石洵瑶', '太原站'],
  '国羽': ['羽毛球', '国羽', '陈雨菲', '石宇奇', '雅思'],
  '网球': ['网球', 'atp', 'wta', '郑钦文', '张帅', '德约科维奇', '阿尔卡拉斯', '斯图加特'],
  '斯诺克': ['斯诺克', '周跃龙', '庞俊旭'],
};

const HOTSPOT_ENTITY_PATTERNS = {
  '勇士': ['勇士', 'warriors'],
  '湖人': ['湖人', 'lakers'],
  '火箭': ['火箭', 'rockets'],
  '凯尔特人': ['凯尔特人', 'celtics'],
  '太阳': ['太阳', 'suns'],
  '雷霆': ['雷霆', 'thunder'],
  '尼克斯': ['尼克斯', 'knicks'],
  '快船': ['快船', 'clippers'],
  '魔术': ['魔术', 'magic'],
  '黄蜂': ['黄蜂', 'hornets'],
  '詹姆斯': ['詹姆斯', 'lebron james'],
  '库里': ['库里', 'stephen curry'],
  '杰伦·格林': ['杰伦·格林', 'jalen green'],
  '班凯罗': ['班凯罗', 'paolo banchero'],
  '东契奇': ['东契奇', 'luka doncic'],
  '约基奇': ['约基奇', 'nikola jokic'],
  '国足': ['国足'],
  '利物浦': ['利物浦', 'liverpool'],
  '拜仁': ['拜仁', 'bayern'],
  '阿森纳': ['阿森纳', 'arsenal'],
  '皇马': ['皇马', '皇家马德里', 'real madrid'],
  '巴萨': ['巴萨', '巴塞罗那', 'barcelona'],
  '姆巴佩': ['姆巴佩', 'mbappe'],
  '王楚钦': ['王楚钦'],
  '孙颖莎': ['孙颖莎'],
  '郑钦文': ['郑钦文'],
  '张帅': ['张帅'],
  '陈雨菲': ['陈雨菲'],
  '中国女篮': ['中国女篮'],
  '山西女篮': ['山西女篮'],
  '四川女篮': ['四川女篮'],
  '成都蓉城': ['成都蓉城'],
  '北京国安': ['北京国安'],
  '山东泰山': ['山东', '泰山'],
  '上海海港': ['海港', '上海海港'],
  '天津津门虎': ['津门虎'],
  '青岛海牛': ['海牛'],
  '赵继伟': ['赵继伟'],
  '王哲林': ['王哲林'],
  '程帅澎': ['程帅澎'],
  '高诗岩': ['高诗岩'],
  '韦世豪': ['韦世豪'],
  '廖力生': ['廖力生'],
  '黄友政': ['黄友政'],
  '石洵瑶': ['石洵瑶'],
  '周跃龙': ['周跃龙'],
  '庞俊旭': ['庞俊旭'],
  '冉珂嘉': ['冉珂嘉'],
};

const HOTSPOT_DOMESTIC_PRIORITY_PATTERNS = [
  '中国', '中国女篮', '中国男篮', '中国球员', '中国选手', '国足', '国乒', '国羽', '中超',
  '足协杯', 'CBA', 'WCBA', '女篮世界杯', 'WTT', '太原站', '斯诺克', '郑钦文', '张帅',
  '赵继伟', '韦世豪', '周跃龙', '庞俊旭',
];

const HOTSPOT_DOMESTIC_PRIORITY_LEAGUES = new Set(['CBA', 'WCBA', '中超', '中国女篮', '国乒', '国羽', '斯诺克']);
const HOTSPOT_DOMESTIC_PRIORITY_ENTITIES = new Set([
  '中国女篮', '山西女篮', '四川女篮', '成都蓉城', '北京国安', '山东泰山', '上海海港', '天津津门虎',
  '青岛海牛', '赵继伟', '王哲林', '程帅澎', '高诗岩', '韦世豪', '廖力生', '黄友政', '石洵瑶',
  '周跃龙', '庞俊旭', '冉珂嘉', '王楚钦', '孙颖莎', '郑钦文', '张帅', '陈雨菲',
]);

const HOTSPOT_BLOCKED_SOURCES = new Set(['facebook', '腾讯体育社区', '新浪网']);
const HOTSPOT_BLOCKED_TITLE_PATTERNS = [
  /^(NBA|CBA|WCBA|WTT|中超)$/i,
  /看NBA足球网球赛车NFL/,
  /社区·汇聚心跳/,
  /^\d{1,2}-\d{1,2}:/,
  /^\[[^\]]+\]/,
  /^\[图\]/,
  /\bprep talk\b/i,
  /\bhow to buy\b/i,
  /\bhow to watch\b/i,
  /\bwhere to watch\b/i,
  /\bprediction(s)?\b/i,
  /\bodds\b/i,
  /\bprop bets?\b/i,
  /\btickets?\b/i,
  /视频集锦/,
  /集锦/,
  /比赛回顾/,
  /回放/,
  /录像/,
  /图集/,
  /门票/,
  /赔率/,
  /购彩/,
  /直播/,
  /哪里看/,
  /免费观看/,
  /预测/,
  /胜率/,
  /有资格/,
  /有过/,
  /都有谁/,
  /还会回来吗/,
  /诸神黄昏/,
  /常胜将军/,
  /往年/,
  /历史第/,
  /第\d+次出现/,
  /明天稳了/,
  /ESPN/i,
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('体育热点')
    .addItem('立即刷新热点', 'refreshSportsHotspots')
    .addItem('安装每日刷新', 'installDailyTrigger')
    .addItem('删除每日刷新', 'removeDailyTrigger')
    .addToUi();
}

function refreshSportsHotspots() {
  const referenceTime = new Date();
  const allItems = [];
  HOTSPOT_CONFIG.querySpecs.forEach((spec) => {
    fetchQuery_(spec).forEach((item) => allItems.push(item));
  });

  const mergedItems = mergeItems_(allItems);
  const rankedItems = rankItems_(mergedItems, referenceTime);
  const finalItems = filterRanked_(rankedItems, referenceTime);
  writeSheetRows_(finalItems, referenceTime);
}

function installDailyTrigger() {
  removeDailyTrigger();
  ScriptApp.newTrigger('refreshSportsHotspots')
    .timeBased()
    .everyDays(1)
    .atHour(HOTSPOT_CONFIG.dailyHour)
    .create();
}

function removeDailyTrigger() {
  ScriptApp.getProjectTriggers().forEach((trigger) => {
    if (trigger.getHandlerFunction() === 'refreshSportsHotspots') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}

function fetchQuery_(spec) {
  const response = UrlFetchApp.fetch(buildGoogleNewsUrl_(spec.query), {
    muteHttpExceptions: true,
    headers: HOTSPOT_HEADERS,
  });
  const status = response.getResponseCode();
  if (status !== 200) {
    throw new Error('Google News RSS fetch failed for "' + spec.name + '" with status ' + status);
  }
  return parseFeedXml_(response.getContentText(), spec);
}

function parseFeedXml_(xmlText, spec) {
  const doc = XmlService.parse(xmlText);
  const root = doc.getRootElement();
  const channel = root.getChild('channel');
  if (!channel) {
    return [];
  }

  return channel.getChildren('item').map((item) => {
    const sourceNode = item.getChild('source');
    const sourceName = sourceNode ? safeText_(sourceNode.getText()) : '';
    const rawTitle = safeText_(item.getChildText('title'));
    const title = splitTitle_(rawTitle, sourceName);
    if (!title || shouldSkip_(title, sourceName) || !queryMatchesTitle_(title, spec)) {
      return null;
    }

    const sourceUrlAttr = sourceNode ? sourceNode.getAttribute('url') : null;
    const publishedAt = parsePubDate_(safeText_(item.getChildText('pubDate')));

    return {
      title: title,
      summary: '',
      source: sourceName,
      url: safeText_(item.getChildText('link')),
      published_at: publishedAt,
      latest_published_at: publishedAt,
      league: spec.league,
      query_name: spec.name,
      query: spec.query,
      sources: sourceName ? [{name: sourceName, url: sourceUrlAttr ? sourceUrlAttr.getValue() : ''}] : [],
    };
  }).filter(Boolean);
}

function buildGoogleNewsUrl_(query) {
  return 'https://news.google.com/rss/search?q=' + encodeURIComponent(query) + '&hl=zh-CN&gl=CN&ceid=CN:zh-Hans';
}

function parsePubDate_(value) {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (isNaN(parsed.getTime())) {
    return '';
  }
  return toIsoString_(parsed);
}

function queryMatchesTitle_(title, spec) {
  const required = spec.required_keywords || [];
  if (!required.length) {
    return true;
  }
  const loweredTitle = String(title || '').toLowerCase();
  return required.some((keyword) => loweredTitle.indexOf(String(keyword).toLowerCase()) >= 0);
}

function splitTitle_(title, sourceName) {
  const suffix = sourceName ? ' - ' + sourceName : '';
  if (suffix && title.endsWith(suffix)) {
    return title.slice(0, -suffix.length).trim();
  }
  return title.trim();
}

function shouldSkip_(title, sourceName) {
  if (String(title || '').trim().length <= 4) {
    return true;
  }
  const loweredSource = String(sourceName || '').trim().toLowerCase();
  if (loweredSource && HOTSPOT_BLOCKED_SOURCES.has(loweredSource)) {
    return true;
  }
  return HOTSPOT_BLOCKED_TITLE_PATTERNS.some((pattern) => pattern.test(title));
}

function mergeItems_(items) {
  const merged = {};

  items.forEach((item) => {
    const key = normalizeTitle_(item.title);
    if (!merged[key]) {
      merged[key] = {
        title: item.title,
        summary: item.summary,
        source: item.source,
        url: item.url,
        published_at: item.published_at,
        latest_published_at: item.latest_published_at,
        league: Array.isArray(item.league) ? item.league.slice() : (item.league ? [item.league] : []),
        query_name: item.query_name,
        query: item.query,
        sources: Array.isArray(item.sources) ? item.sources.slice() : [],
      };
      return;
    }

    const existing = merged[key];
    const known = new Set(existing.sources.map((source) => String(source.name || '').trim().toLowerCase()).filter(Boolean));
    (item.sources || []).forEach((source) => {
      const name = String(source.name || '').trim().toLowerCase();
      if (name && !known.has(name)) {
        existing.sources.push(source);
        known.add(name);
      }
    });

    const leagueValues = []
      .concat(existing.league || [])
      .concat(item.league || [])
      .filter(Boolean);
    existing.league = uniqueInOrder_(leagueValues);

    const existingLatest = parseIsoDate_(existing.latest_published_at || existing.published_at);
    const currentLatest = parseIsoDate_(item.latest_published_at || item.published_at);
    if (currentLatest && (!existingLatest || currentLatest.getTime() > existingLatest.getTime())) {
      existing.latest_published_at = item.latest_published_at;
      existing.published_at = item.published_at;
      existing.source = item.source;
      existing.url = item.url;
    }
  });

  return Object.keys(merged).map((key) => merged[key]);
}

function rankItems_(items, referenceTime) {
  return items
    .map((item) => enrichItem_(item, referenceTime))
    .sort((left, right) => {
      if (right.total_score !== left.total_score) {
        return right.total_score - left.total_score;
      }
      if (right.score_breakdown.hotness_score !== left.score_breakdown.hotness_score) {
        return right.score_breakdown.hotness_score - left.score_breakdown.hotness_score;
      }
      return String(right.latest_published_at || '').localeCompare(String(left.latest_published_at || ''));
    });
}

function filterRanked_(items, referenceTime) {
  function collect(maxAgeHours) {
    return items.filter((item) => {
      if (item.total_score < HOTSPOT_CONFIG.minScore || item.topic_type === 'sports_low_value') {
        return false;
      }
      const latest = parseIsoDate_(item.latest_published_at || item.published_at);
      if (!latest) {
        return true;
      }
      const ageHours = (referenceTime.getTime() - latest.getTime()) / 3600000;
      return ageHours <= maxAgeHours;
    });
  }

  let filtered = collect(48);
  if (filtered.length < Math.min(HOTSPOT_CONFIG.topN, 8)) {
    filtered = collect(72);
  }
  if (!filtered.length) {
    filtered = items.slice(0, HOTSPOT_CONFIG.topN);
  }
  return filtered.slice(0, HOTSPOT_CONFIG.topN);
}

function writeSheetRows_(items, referenceTime) {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = getOrCreateSheet_(spreadsheet, HOTSPOT_CONFIG.targetSheetName);
  const timeZone = spreadsheet.getSpreadsheetTimeZone();
  const runDate = Utilities.formatDate(referenceTime, timeZone, 'yyyy-MM-dd');
  const headers = HOTSPOT_CONFIG.sheetColumns.map((entry) => entry[1]);
  const values = items.map((item, index) => [
    runDate,
    index + 1,
    round2_(item.total_score).toFixed(2),
    item.topic_label,
    item.storyline_tags.join('、'),
    item.title,
    item.summary_hint,
    item.source || '',
    item.source_count || 0,
    item.published_at || '',
    item.latest_published_at || '',
    item.league_tags.join('、'),
    item.keyword_hits.join('、'),
    item.entity_tags.join('、'),
    item.why_hot.join('；'),
    item.reference_url || '',
  ]);

  const existingFilter = sheet.getFilter();
  if (existingFilter) {
    existingFilter.remove();
  }

  sheet.clearContents();
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  if (values.length) {
    sheet.getRange(2, 1, values.length, headers.length).setValues(values);
  }
  sheet.setFrozenRows(1);
  sheet.autoResizeColumns(1, headers.length);
  sheet.getRange(1, 1, Math.max(values.length + 1, 2), headers.length).createFilter();
}

function getOrCreateSheet_(spreadsheet, sheetName) {
  const existing = spreadsheet.getSheetByName(sheetName);
  if (existing) {
    return existing;
  }

  const sheets = spreadsheet.getSheets();
  if (sheets.length) {
    return sheets[0];
  }

  return spreadsheet.insertSheet(sheetName, 0);
}

function enrichItem_(item, referenceTime) {
  const titleText = String(item.title || '').toLowerCase();
  const fullText = lowerBlob_(item);
  const rawStoryTags = storylineTags_(titleText, fullText);
  const topic = classifyTopic_(titleText, fullText, rawStoryTags);
  const keywordHits = matchKeywords_(fullText);
  const leagueTags = detectTags_(fullText, item.league, HOTSPOT_LEAGUE_KEYWORDS);
  const entityTags = detectEntities_(fullText, item.entities);
  const parsedTime = parseIsoDate_(item.latest_published_at || item.published_at);
  const freshness = freshnessScore_(parsedTime, referenceTime);
  const totalSources = sourceCount_(item);
  const hotness = hotnessScore_(freshness, keywordHits, entityTags, rawStoryTags, totalSources);
  const topicFit = topicFitScore_(topic.topic_type, topic.confidence);
  const sourceScore = sourceScore_(item.source, totalSources);
  const keywordScore = keywordScore_(keywordHits);
  const titleScore = titleQualityScore_(String(item.title || ''), keywordHits, entityTags);
  const domesticBonus = domesticPriorityBonus_(fullText, leagueTags, entityTags, keywordHits);
  const domesticReason = domesticPriorityReason_(fullText, leagueTags, entityTags);
  const totalScore = round2_(
    Math.min(
      10.0,
      hotness * 0.35 +
        topicFit * 0.25 +
        sourceScore * 0.20 +
        keywordScore * 0.15 +
        titleScore * 0.05 +
        domesticBonus
    )
  );

  return {
    title: item.title || '',
    source: item.source || '',
    source_count: totalSources,
    published_at: item.published_at || '',
    latest_published_at: item.latest_published_at || item.published_at || '',
    topic_type: topic.topic_type,
    topic_label: HOTSPOT_TOPIC_LABELS[topic.topic_type],
    storyline_tags: rawStoryTags.map((tag) => HOTSPOT_STORYLINE_LABELS[tag]),
    summary_hint: buildSummaryHint_(item.title || '', topic.topic_type, leagueTags, entityTags, rawStoryTags, keywordHits),
    keyword_hits: keywordHits,
    league_tags: leagueTags,
    entity_tags: entityTags,
    score_breakdown: {
      hotness_score: hotness,
      topic_fit_score: topicFit,
      source_score: sourceScore,
      keyword_score: keywordScore,
      title_quality_score: titleScore,
      domestic_bonus: domesticBonus,
    },
    total_score: totalScore,
    why_hot: buildWhyHot_(item.source, hotness, topic.topic_type, keywordHits, entityTags, totalSources, rawStoryTags, domesticReason),
    reference_url: item.url || '',
    domestic_priority: domesticBonus >= 0.8,
  };
}

function storylineTags_(titleText, fullText) {
  const combined = (titleText + ' ' + fullText).trim();
  const tags = [];
  Object.keys(HOTSPOT_STORYLINE_PATTERNS).forEach((tag) => {
    if (HOTSPOT_STORYLINE_PATTERNS[tag].some((pattern) => containsPattern_(combined, pattern))) {
      tags.push(tag);
    }
  });
  if (containsPattern_(combined, 'vs') || containsPattern_(combined, '对阵')) {
    tags.push('lineup');
  }
  if (/\d+\s*-\s*\d+/.test(combined)) {
    tags.push('result');
  }
  return uniqueInOrder_(tags);
}

function classifyTopic_(titleText, fullText, storyTags) {
  const previewSignal = HOTSPOT_STORYLINE_PATTERNS.lineup.filter((pattern) => containsPattern_(fullText, pattern)).length;
  const resultSignal = HOTSPOT_STORYLINE_PATTERNS.result.filter((pattern) => containsPattern_(fullText, pattern)).length;
  const starSignal = HOTSPOT_STORYLINE_PATTERNS.star.filter((pattern) => containsPattern_(fullText, pattern)).length;
  const businessSignal = HOTSPOT_STORYLINE_PATTERNS.business.filter((pattern) => containsPattern_(fullText, pattern)).length;

  const topicScores = {
    sports_result: resultSignal * 2.2 + (storyTags.indexOf('result') >= 0 ? 1.2 : 0.0),
    sports_preview: previewSignal * 2.0 + (storyTags.indexOf('lineup') >= 0 ? 1.3 : 0.0),
    sports_star: starSignal * 1.8 + storyTags.filter((tag) => ['transfer', 'injury', 'star', 'controversy'].indexOf(tag) >= 0).length * 1.1,
    sports_business: businessSignal * 2.2 + (storyTags.indexOf('business') >= 0 ? 1.0 : 0.0),
    sports_low_value: 1.0,
  };

  if (containsPattern_(titleText, 'vs') || containsPattern_(titleText, '对阵')) {
    topicScores.sports_preview += 1.4;
  }
  if (['赛前', '首发', '名单', '前瞻', '迎战'].some((marker) => containsPattern_(fullText, marker))) {
    topicScores.sports_preview += 1.2;
  }
  if (['抽签', '分档', '名单公布'].some((marker) => containsPattern_(fullText, marker))) {
    topicScores.sports_preview += 1.0;
  }
  if (['战胜', '击败', '不敌', '晋级', '淘汰', '出局', '无缘', '绝杀'].some((marker) => containsPattern_(fullText, marker))) {
    topicScores.sports_result += 1.4;
  }
  if (/\d+\s*-\s*\d+/.test(fullText)) {
    topicScores.sports_result += 1.2;
  }
  if (['砍下', '三双', '纪录', '里程碑', '帽子戏法', '双响'].some((marker) => containsPattern_(fullText, marker))) {
    topicScores.sports_star += 1.2;
  }

  let bestTopic = 'sports_low_value';
  Object.keys(topicScores).forEach((topic) => {
    if (topicScores[topic] > topicScores[bestTopic]) {
      bestTopic = topic;
    }
  });
  return {topic_type: bestTopic, confidence: topicScores[bestTopic]};
}

function matchKeywords_(text) {
  const matches = [];
  HOTSPOT_KEYWORD_RULES.forEach((rule) => {
    if (rule.patterns.some((pattern) => containsPattern_(text, pattern))) {
      matches.push(rule.label);
    }
  });
  return matches.sort((left, right) => {
    if (HOTSPOT_KEYWORD_WEIGHTS[right] !== HOTSPOT_KEYWORD_WEIGHTS[left]) {
      return HOTSPOT_KEYWORD_WEIGHTS[right] - HOTSPOT_KEYWORD_WEIGHTS[left];
    }
    return left.localeCompare(right);
  });
}

function detectTags_(text, explicit, mapping) {
  const matches = [];
  Object.keys(mapping).forEach((label) => {
    if (mapping[label].some((pattern) => containsPattern_(text, pattern))) {
      matches.push(label);
    }
  });
  if (typeof explicit === 'string' && explicit) {
    matches.push(displayText_(explicit));
  } else if (Array.isArray(explicit)) {
    explicit.forEach((value) => {
      if (value) {
        matches.push(displayText_(value));
      }
    });
  }
  return uniqueInOrder_(matches);
}

function detectEntities_(text, explicit) {
  const matches = [];
  if (typeof explicit === 'string' && explicit) {
    matches.push(displayText_(explicit));
  } else if (Array.isArray(explicit)) {
    explicit.forEach((value) => {
      if (value) {
        matches.push(displayText_(value));
      }
    });
  }
  Object.keys(HOTSPOT_ENTITY_PATTERNS).forEach((label) => {
    if (HOTSPOT_ENTITY_PATTERNS[label].some((pattern) => containsPattern_(text, pattern))) {
      matches.push(label);
    }
  });
  return uniqueInOrder_(matches);
}

function sourceCount_(item) {
  if (typeof item.source_count === 'number' && item.source_count > 0) {
    return item.source_count;
  }
  if (Array.isArray(item.sources)) {
    const names = new Set(item.sources.map((source) => String(source.name || '').trim().toLowerCase()).filter(Boolean));
    if (names.size) {
      return names.size;
    }
  }
  return item.source ? 1 : 0;
}

function sourceWeight_(source) {
  if (!source) {
    return 2.5;
  }
  const lowered = String(source).toLowerCase();
  const key = Object.keys(HOTSPOT_SOURCE_WEIGHTS).find((name) => lowered.indexOf(String(name).toLowerCase()) >= 0);
  return key ? HOTSPOT_SOURCE_WEIGHTS[key] * 3 : 3.5;
}

function freshnessScore_(publishedAt, referenceTime) {
  if (!publishedAt) {
    return 3.0;
  }
  const ageHours = Math.max(0, (referenceTime.getTime() - publishedAt.getTime()) / 3600000);
  let score;
  if (ageHours <= 2) {
    score = 10.0 - ageHours * 0.4;
  } else if (ageHours <= 6) {
    score = 9.2 - (ageHours - 2) * 0.45;
  } else if (ageHours <= 12) {
    score = 7.4 - (ageHours - 6) * 0.35;
  } else if (ageHours <= 24) {
    score = 5.3 - (ageHours - 12) * 0.18;
  } else if (ageHours <= 48) {
    score = 3.1 - (ageHours - 24) * 0.08;
  } else {
    score = 1.0;
  }
  return round2_(Math.max(0.6, Math.min(10.0, score)));
}

function keywordScore_(keywordHits) {
  const total = keywordHits.reduce((sum, keyword) => sum + HOTSPOT_KEYWORD_WEIGHTS[keyword], 0);
  return round2_(Math.min(10.0, total * 1.35));
}

function topicFitScore_(topicType, confidence) {
  const baselines = {
    sports_result: 7.8,
    sports_preview: 7.2,
    sports_star: 7.0,
    sports_business: 6.8,
    sports_low_value: 2.0,
  };
  return round2_(Math.min(10.0, Math.max(0.5, baselines[topicType] + Math.min(2.0, confidence * 0.35))));
}

function hotnessScore_(freshness, keywordHits, entityTags, storyTags, sourceTotal) {
  const strongHits = keywordHits.filter((keyword) => HOTSPOT_STRONG_EVENT_KEYWORDS.has(keyword)).length;
  const eventStrength = Math.min(10.0, strongHits * 1.8 + storyTags.length * 1.0 + Math.min(entityTags.length, 3) * 0.8);
  const spreadBonus = Math.min(2.0, Math.max(0, sourceTotal - 1) * 0.8);
  return round2_(Math.min(10.0, Math.max(0.5, freshness * 0.6 + eventStrength * 0.3 + spreadBonus)));
}

function sourceScore_(sourceName, sourceTotal) {
  const credibility = sourceWeight_(sourceName);
  let diversity = 0.5;
  if (sourceTotal === 2) {
    diversity = 1.8;
  } else if (sourceTotal === 3) {
    diversity = 2.8;
  } else if (sourceTotal >= 4) {
    diversity = 3.8;
  }
  return round2_(Math.min(10.0, credibility + diversity));
}

function titleQualityScore_(title, keywordHits, entityTags) {
  const length = String(title || '').trim().length;
  let score = 5.0;
  if (length >= 18 && length <= 52) {
    score += 2.0;
  } else if (length > 80 || length < 10) {
    score -= 1.5;
  }
  if (keywordHits.length) {
    score += Math.min(2.0, keywordHits.length * 0.5);
  }
  if (entityTags.length) {
    score += 1.0;
  }
  const genericMarkers = ['最新', '资讯', '消息', 'news', 'latest', 'report'];
  if (genericMarkers.filter((marker) => containsPattern_(title, marker)).length >= 2) {
    score -= 1.5;
  }
  return round2_(Math.min(10.0, Math.max(1.0, score)));
}

function domesticPriorityBonus_(text, leagueTags, entityTags, keywordHits) {
  const matchedPatterns = HOTSPOT_DOMESTIC_PRIORITY_PATTERNS.filter((pattern) => containsPattern_(text, pattern)).length;
  let score = Math.min(1.6, matchedPatterns * 0.35);
  if (leagueTags.some((tag) => HOTSPOT_DOMESTIC_PRIORITY_LEAGUES.has(tag))) {
    score += 0.85;
  }
  if (entityTags.some((entity) => HOTSPOT_DOMESTIC_PRIORITY_ENTITIES.has(entity))) {
    score += 0.85;
  }
  if (keywordHits.some((keyword) => ['中超', 'CBA', '中国女篮', '中国球员', 'WTT', '斯诺克', '国乒', '国羽'].indexOf(keyword) >= 0)) {
    score += 0.45;
  }
  return round2_(Math.min(2.4, score));
}

function domesticPriorityReason_(text, leagueTags, entityTags) {
  if (['中国女篮', '中国男篮', '国足', '国乒', '国羽', '中国球员', '中国选手'].some((pattern) => containsPattern_(text, pattern))) {
    return '国字号/中国选手关注度高';
  }
  if (leagueTags.some((tag) => ['CBA', 'WCBA', '中超'].indexOf(tag) >= 0)) {
    return '本土联赛优先级更高';
  }
  if (entityTags.some((entity) => HOTSPOT_DOMESTIC_PRIORITY_ENTITIES.has(entity))) {
    return '本土球队和中国球员更易形成讨论';
  }
  return '';
}

function shortTitleLead_(title) {
  const compact = String(title || '').trim().replace(/[。！!？?\s]+$/g, '');
  const separators = ['：', ':', '，', ',', '｜', '|'];
  for (let i = 0; i < separators.length; i += 1) {
    const head = compact.split(separators[i], 1)[0].trim();
    if (head.length >= 8 && head.length <= 30) {
      return head;
    }
  }
  if (compact.length <= 28) {
    return compact;
  }
  return compact.slice(0, 24).replace(/[，,:：\s]+$/g, '') + '…';
}

function summaryCore_(title) {
  const compact = String(title || '').replace(/\s+/g, ' ').trim().replace(/[。！!？?]+$/g, '');
  const separators = ['：', ':'];
  for (let i = 0; i < separators.length; i += 1) {
    if (compact.indexOf(separators[i]) >= 0) {
      const tail = compact.split(separators[i]).slice(1).join(separators[i]).trim();
      if (tail.length >= 6) {
        return tail;
      }
    }
  }
  return compact;
}

function buildSummaryHint_(title, topicType, leagueTags, entityTags, storyTags, keywordHits) {
  const core = summaryCore_(title);
  const lead = shortTitleLead_(title);
  if (storyTags.indexOf('transfer') >= 0) {
    return core + '，转会进展已经明朗，重点看官宣节奏、合同细节和阵容补强效果。';
  }
  if (storyTags.indexOf('injury') >= 0) {
    return core + '，重点看伤情级别、复出时间和替代方案是否稳定。';
  }
  if (storyTags.indexOf('controversy') >= 0) {
    return core + '，争议焦点已经形成，重点看官方回应和后续处理结果。';
  }
  if (['获四冠', '夺冠', '问鼎', '冠军'].some((marker) => containsPattern_(title, marker))) {
    return core + '，成绩已经兑现，重点看含金量、下一站签表和状态延续。';
  }
  if (['位列第二档', '名单公布', '入围', '选中'].some((marker) => containsPattern_(title, marker))) {
    return core + '，名单或分档已经落定，重点看签表位置、出场机会和后续赛程。';
  }
  if (['淘汰', '晋级', '出局', '无缘'].some((marker) => containsPattern_(title, marker))) {
    return core + '，胜负结果已经落地，重点看下一轮对手和后续走势变化。';
  }
  if (['大胜', '完胜', '险胜', '不敌', '战平', '绝杀', '逆转'].some((marker) => containsPattern_(title, marker))) {
    return core + '，比赛拐点已经明确，重点看核心表现和接下来一轮的影响。';
  }
  if (containsPattern_(title, '附加赛')) {
    return core + '，席位争夺已经进入关键阶段，重点看落位变化和后续对阵。';
  }
  if (keywordHits.some((keyword) => ['晋级', '淘汰', '出局', '决赛', '半决赛'].indexOf(keyword) >= 0)) {
    return core + '，关键结果已经产生，重点看晋级形势和下一阶段对阵。';
  }
  if (keywordHits.some((keyword) => ['绝杀', '逆转', '季后赛', '附加赛'].indexOf(keyword) >= 0)) {
    return core + '，热度主要来自比赛转折，重点看核心球员表现和排名影响。';
  }
  if (['中国', '国乒', '国羽', '中超', 'CBA', 'WCBA', '斯诺克'].some((marker) => containsPattern_(title, marker))) {
    return core + '，国内关注度较高，重点看签表、排名或联赛走势的后续变化。';
  }
  if (topicType === 'sports_preview') {
    return core + '，赛前变数仍在，重点看首发名单、伤病变化和临场调整。';
  }
  if (topicType === 'sports_star') {
    const focus = entityTags[0] || leagueTags[0] || '焦点人物';
    return core + '，重点看' + focus + '的表现含金量以及对后续走势的带动作用。';
  }
  if (topicType === 'sports_business') {
    return core + '，重点看合作细节、商业价值和联赛层面的延伸影响。';
  }
  return lead + '，重点看结果落地后的排名变化和后续连锁反应。';
}

function buildWhyHot_(itemSource, hotness, topicType, keywordHits, entityTags, sourceTotal, rawStoryTags, domesticReason) {
  const reasons = [];
  if (hotness >= 8.0) {
    reasons.push('6小时内更新');
  } else if (hotness >= 6.0) {
    reasons.push('当天持续发酵');
  }

  const topicReason = {
    sports_result: '赛果明确，传播面大',
    sports_preview: '赛前关注度高',
    sports_star: '人物带动讨论',
    sports_business: '商业话题延展性强',
    sports_low_value: '相关性存在但优先级偏低',
  };
  reasons.push(topicReason[topicType]);

  if (domesticReason) {
    reasons.push(domesticReason);
  }
  if (keywordHits.length) {
    reasons.push('关键词：' + keywordHits.slice(0, 3).join('、'));
  }
  if (entityTags.length) {
    reasons.push('主体：' + entityTags.slice(0, 3).join('、'));
  }
  if (rawStoryTags.length) {
    reasons.push('标签：' + rawStoryTags.slice(0, 3).map((tag) => HOTSPOT_STORYLINE_LABELS[tag]).join('、'));
  }
  if (sourceTotal > 1) {
    reasons.push(sourceTotal + '个来源交叉出现');
  }
  if (itemSource) {
    reasons.push('来源：' + itemSource);
  }
  return reasons;
}

function lowerBlob_(item) {
  return String(item.title || '') + ' ' + String(item.summary || '');
}

function displayText_(value) {
  const compact = String(value || '').replace(/\s+/g, ' ').trim();
  if (!compact) {
    return compact;
  }
  if (hasCjk_(compact) || compact === compact.toUpperCase()) {
    return compact;
  }
  return compact.replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizeTitle_(title) {
  return String(title || '')
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function hasCjk_(text) {
  return /[\u4e00-\u9fff]/.test(String(text || ''));
}

function containsPattern_(text, pattern) {
  const haystack = String(text || '').toLowerCase();
  const needle = String(pattern || '').toLowerCase();
  if (!needle) {
    return false;
  }
  if (hasCjk_(needle)) {
    return haystack.indexOf(needle) >= 0;
  }
  return new RegExp('(^|[^a-z0-9])' + escapeRegex_(needle) + '([^a-z0-9]|$)', 'i').test(haystack);
}

function parseIsoDate_(value) {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return isNaN(parsed.getTime()) ? null : parsed;
}

function toIsoString_(date) {
  return Utilities.formatDate(date, Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ssXXX");
}

function safeText_(value) {
  return String(value || '').trim();
}

function uniqueInOrder_(values) {
  const ordered = [];
  const seen = new Set();
  values.forEach((value) => {
    const key = String(value);
    if (!key || seen.has(key)) {
      return;
    }
    seen.add(key);
    ordered.push(value);
  });
  return ordered;
}

function round2_(value) {
  return Math.round(Number(value) * 100) / 100;
}

function escapeRegex_(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
