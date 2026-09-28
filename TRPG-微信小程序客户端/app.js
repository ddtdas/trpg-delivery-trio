const strings = require('./strings')

App({
  globalData: {
    appName: strings['title'],
    clientVersion: '1.0.0',
    navLabels: [strings['nav.setup'], strings['nav.table'], strings['nav.voice']]
  }
})
