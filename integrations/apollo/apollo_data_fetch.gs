// --- CRAWLER SETTINGS ---
const START_YEAR = 2023;
const START_MONTH = 8; // 11 = December
const END_YEAR = 2022;
const END_MONTH = 9;    // 9 = October
const CALL_LIMIT = 350; // API calls per hour safety limit

/**
 * STEP 1: RUN THIS ONCE TO SET THE STARTING POINT
 */
function initializeCrawler() {
  const props = PropertiesService.getScriptProperties();
  props.setProperties({
    'C_YEAR': START_YEAR.toString(),
    'C_MONTH': START_MONTH.toString(),
    'C_CAMP_IDX': '0',
    'C_PAGE': '1',
    'IS_COMPLETE': 'false'
  });
  console.log("Crawler initialized. Target: Dec 2025 down to Oct 2023.");
}

/**
 * STEP 2: SET THIS ON AN HOURLY TRIGGER
 */
function syncHistoricalDatabase() {
  const startTime = new Date().getTime();
  const props = PropertiesService.getScriptProperties();
  
  if (props.getProperty('IS_COMPLETE') === 'true') {
    console.log("Historical crawl already finished.");
    return;
  }

  const apiKey = props.getProperty('APOLLO_API_KEY');
  const baseUrl = 'https://api.apollo.io/api/v1/emailer_messages';
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName('EntireHistoricalData');

  // Create sheet if it doesn't exist
  if (!sheet) {
    sheet = ss.insertSheet('EntireHistoricalData');
    sheet.appendRow([
      "Message ID", "First Name", "Last Name", "LinkedIn URL", "Recipient", "Title", "City", "Subject", "Campaign Name", 
      "Opens", "Clicks", "Replied?", "Status", "Email Status", "Sent At", "Last Opened At", "Lead Category"
    ]);
    sheet.setFrozenRows(1);
  }

  // Load existing IDs for performance
  const idMap = new Map();
  const fullData = sheet.getDataRange().getValues();
  for (let i = 1; i < fullData.length; i++) {
    const idStr = String(fullData[i][0]).trim();
    if (idStr) idMap.set(idStr, i + 1);
  }

  // Load State from Memory
  let year = parseInt(props.getProperty('C_YEAR'));
  let month = parseInt(props.getProperty('C_MONTH'));
  let campIdx = parseInt(props.getProperty('C_CAMP_IDX'));
  let pageNum = parseInt(props.getProperty('C_PAGE'));
  let apiCounter = 0;

  const toIST = (dateStr) => {
    if (!dateStr || dateStr === "N/A") return "N/A";
    try {
      const date = new Date(dateStr);
      return Utilities.formatDate(date, "GMT+5:30", "dd/MM/yyyy HH:mm:ss");
    } catch (e) { return dateStr; }
  };

  while (year >= END_YEAR) {
    // 1. Fetch Campaigns for current month
    const campUrl = `https://api.apollo.io/api/v1/emailer_campaigns/search?per_page=100`;
    const campResp = UrlFetchApp.fetch(campUrl, { "headers": { "X-Api-Key": apiKey }});
    apiCounter++;
    
    const allCampaigns = JSON.parse(campResp.getContentText()).emailer_campaigns || [];
    const targetCampaigns = allCampaigns.filter(c => {
      const d = new Date(c.created_at);
      return d.getFullYear() === year && d.getMonth() === month;
    });

    // Skip month if empty
    if (targetCampaigns.length === 0 || campIdx >= targetCampaigns.length) {
      const nextDate = getPreviousMonth(year, month);
      year = nextDate.year; month = nextDate.month; campIdx = 0; pageNum = 1;
      saveState(props, year, month, campIdx, pageNum);
      if (year < END_YEAR || (year === END_YEAR && month < END_MONTH)) break;
      continue; 
    }

    // 2. Process Campaigns
    for (let i = campIdx; i < targetCampaigns.length; i++) {
      const campaign = targetCampaigns[i];
      let hasNextPage = true;

      while (hasNextPage) {
        // Exit if near Google's 6-min limit
        if (new Date().getTime() - startTime > 240000) { 
          saveState(props, year, month, i, pageNum);
          finalizeSync(sheet);
          return;
        }

        const msgUrl = `${baseUrl}/search?emailer_campaign_ids[]=${campaign.id}&per_page=100&page=${pageNum}`;
        const msgResp = UrlFetchApp.fetch(msgUrl, { "headers": { "X-Api-Key": apiKey }});
        apiCounter++;
        
        const result = JSON.parse(msgResp.getContentText());
        const messages = result.emailer_messages || [];
        
        for (const msg of messages) {
          if (apiCounter >= CALL_LIMIT) {
            saveState(props, year, month, i, pageNum);
            finalizeSync(sheet);
            return;
          }

          if (idMap.has(String(msg.id).trim())) continue;

          try {
            Utilities.sleep(250); 
            const actResp = UrlFetchApp.fetch(`${baseUrl}/${msg.id}/activities`, {
              "headers": { "X-Api-Key": apiKey }, "muteHttpExceptions": true
            });
            apiCounter++;
            const data = JSON.parse(actResp.getContentText());

            // --- TRIPLE-PATH OPEN/CLICK LOGIC ---
            let numOpens = data.num_opens || 0;
            let numClicks = data.num_clicks || 0;
            if (data.emailer_message) {
              numOpens = Math.max(numOpens, data.emailer_message.num_opens || 0);
              numClicks = Math.max(numClicks, data.emailer_message.num_clicks || 0);
            }
            if (data.activities) {
              data.activities.forEach(act => {
                if (act.emailer_message) {
                  numOpens = Math.max(numOpens, act.emailer_message.num_opens || 0);
                  numClicks = Math.max(numClicks, act.emailer_message.num_clicks || 0);
                }
              });
            }

            // --- LAST OPENED FALLBACK ---
            let lastOpenedAtRaw = data.last_opened_at || "N/A";
            if (data.activities && data.activities.length > 0 && lastOpenedAtRaw === "N/A") {
              const firstAct = data.activities[0];
              if (firstAct.emailer_message_events && firstAct.emailer_message_events.length > 0) {
                lastOpenedAtRaw = firstAct.emailer_message_events[0].created_at;
              }
            }

            const em = data.emailer_message || {};
            const contact = em.contact || {};
            
            // --- LEAD CATEGORY RULES ---
            let category = "Cold";
            if (numOpens >= 3) { category = "WARM"; } 
            else if (numOpens === 2) { category = "Engaged"; }

            const rowData = [
              String(msg.id), contact.first_name || "N/A", contact.last_name || "N/A", contact.linkedin_url || "N/A",
              em.to_email || msg.to_email, contact.title || "N/A", contact.city || "N/A", em.subject || msg.subject,
              campaign.name, numOpens, numClicks, 
              (data.replied || em.replied || em.status === 'replied') ? "Yes" : "No",
              em.status || msg.status, contact.email_status || "N/A",
              toIST(em.completed_at || msg.completed_at), toIST(lastOpenedAtRaw), category
            ];

            sheet.appendRow(rowData);
            if (rowData[11] === "Yes") sheet.getRange(sheet.getLastRow(), 12).setBackground("#d9ead3").setFontColor("#274e13");
          } catch (e) { console.log("Skip ID " + msg.id + ": " + e.message); }
        }

        if (messages.length < 100) { hasNextPage = false; pageNum = 1; } 
        else { pageNum++; }
      }
    }
    
    // Move to previous month
    const nextDate = getPreviousMonth(year, month);
    year = nextDate.year; month = nextDate.month; campIdx = 0; pageNum = 1;
    saveState(props, year, month, campIdx, pageNum);
    finalizeSync(sheet);
    if (year < END_YEAR || (year === END_YEAR && month < END_MONTH)) break;
  }
  props.setProperty('IS_COMPLETE', 'true');
  console.log("Historical Database Sync Complete.");
}

function getPreviousMonth(y, m) {
  if (m === 0) return { year: y - 1, month: 11 };
  return { year: y, month: m - 1 };
}

function saveState(props, y, m, c, p) {
  props.setProperties({ 'C_YEAR': y.toString(), 'C_MONTH': m.toString(), 'C_CAMP_IDX': c.toString(), 'C_PAGE': p.toString() });
}

function finalizeSync(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    sheet.getRange(2, 1, lastRow - 1, 17).sort({column: 15, ascending: false});
  }
  const nowIST = Utilities.formatDate(new Date(), "GMT+5:30", "dd/MM/yyyy HH:mm:ss");
  sheet.getRange("S1").setValue("Last Checkpoint (IST): " + nowIST)
       .setFontWeight("bold").setBackground("#efefef").setBorder(true, true, true, true, null, null);
}