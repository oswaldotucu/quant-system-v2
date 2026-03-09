#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// Exports OHLCV data for micro (MNQ, MES, MGC) and mini (NQ, ES, GC)
    /// futures across 1m, 5m, 15m timeframes to CSV files compatible with
    /// quant-system-v2.
    ///
    /// APPEND-ONLY: On chart load, reads the last timestamp from each existing
    /// CSV and only writes bars newer than that. This prevents data loss when
    /// NinjaTrader reboots and loads limited chart history (e.g., 5 days).
    ///
    /// Usage:
    ///   1. Add this indicator to ANY chart (e.g., MNQ 1-minute)
    ///   2. Set OutputDirectory to your synced folder (Dropbox/OneDrive/etc.)
    ///   3. It subscribes to all 18 instrument/timeframe combos via AddDataSeries()
    ///   4. On chart load: appends only bars newer than existing data
    ///   5. On each bar close: appends one line per series
    ///
    /// Output layout (matches quant-system-v2 data/raw/ structure):
    ///   {OutputDirectory}/micro/MNQ_1m.csv
    ///   {OutputDirectory}/mini/NQ_1m.csv
    ///
    /// CSV format:
    ///   datetime,open,high,low,close,volume
    ///   2024-01-02 18:00:00,16850.25,16855.00,16848.50,16852.75,142
    ///
    /// Timestamps are explicitly converted to US/Eastern regardless of
    /// NinjaTrader's configured timezone.
    ///
    /// Contracts are resolved dynamically using the current front-month
    /// roll schedule — no manual updates needed on contract expiry.
    /// </summary>
    public class CsvExporter : Indicator
    {
        // Maps BarsInProgress index -> (subfolder, ticker, timeframe, filename)
        private Dictionary<int, (string Subfolder, string Ticker, string Timeframe, string Filename)> seriesMap;

        // Tracks whether we've initialized each series (read last timestamp from file)
        private HashSet<int> initialized;

        // Last timestamp written per series — bars <= this are skipped (dedup)
        private Dictionary<int, DateTime> lastWrittenTimestamp;

        private TimeZoneInfo easternZone;

        // CME contract months — NinjaTrader uses "SYMBOL MM-YY" format (e.g., "MNQ 03-26")
        // MNQ/MES/NQ/ES: quarterly (Mar, Jun, Sep, Dec)
        // MGC/GC: bimonthly (Feb, Apr, Jun, Aug, Oct, Dec)
        private static readonly int[] ES_NQ_MONTH_NUMS = { 3, 6, 9, 12 };
        private static readonly int[] GC_MONTH_NUMS = { 2, 4, 6, 8, 10, 12 };

        [NinjaScriptProperty]
        [Display(Name = "Output Directory", Description = "Folder for CSV output",
                 Order = 1, GroupName = "Parameters")]
        public string OutputDirectory { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Exports OHLCV to CSV for quant-system-v2 (micro + mini)";
                Name = "CsvExporter";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                OutputDirectory = @"G:\My Drive\QuantFiles\near-realtime";
            }
            else if (State == State.Configure)
            {
                seriesMap = new Dictionary<int, (string, string, string, string)>();
                initialized = new HashSet<int>();
                lastWrittenTimestamp = new Dictionary<int, DateTime>();
                easternZone = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

                // Resolve current front-month contracts dynamically
                string mnqContract = GetFrontMonthContract("MNQ", false);
                string mesContract = GetFrontMonthContract("MES", false);
                string mgcContract = GetFrontMonthContract("MGC", true);
                string nqContract  = GetFrontMonthContract("NQ",  false);
                string esContract  = GetFrontMonthContract("ES",  false);
                string gcContract  = GetFrontMonthContract("GC",  true);

                Print(string.Format("CsvExporter: MNQ={0}, MES={1}, MGC={2}, NQ={3}, ES={4}, GC={5}",
                    mnqContract, mesContract, mgcContract, nqContract, esContract, gcContract));

                // The primary series (BarsInProgress=0) is whatever chart this
                // indicator is added to. We add 18 more series below.

                // --- Micro contracts ---
                AddDataSeries(mnqContract, BarsPeriodType.Minute, 1);   // idx 1
                AddDataSeries(mnqContract, BarsPeriodType.Minute, 5);   // idx 2
                AddDataSeries(mnqContract, BarsPeriodType.Minute, 15);  // idx 3
                AddDataSeries(mesContract, BarsPeriodType.Minute, 1);   // idx 4
                AddDataSeries(mesContract, BarsPeriodType.Minute, 5);   // idx 5
                AddDataSeries(mesContract, BarsPeriodType.Minute, 15);  // idx 6
                AddDataSeries(mgcContract, BarsPeriodType.Minute, 1);   // idx 7
                AddDataSeries(mgcContract, BarsPeriodType.Minute, 5);   // idx 8
                AddDataSeries(mgcContract, BarsPeriodType.Minute, 15);  // idx 9

                // --- Mini contracts ---
                AddDataSeries(nqContract, BarsPeriodType.Minute, 1);    // idx 10
                AddDataSeries(nqContract, BarsPeriodType.Minute, 5);    // idx 11
                AddDataSeries(nqContract, BarsPeriodType.Minute, 15);   // idx 12
                AddDataSeries(esContract, BarsPeriodType.Minute, 1);    // idx 13
                AddDataSeries(esContract, BarsPeriodType.Minute, 5);    // idx 14
                AddDataSeries(esContract, BarsPeriodType.Minute, 15);   // idx 15
                AddDataSeries(gcContract, BarsPeriodType.Minute, 1);    // idx 16
                AddDataSeries(gcContract, BarsPeriodType.Minute, 5);    // idx 17
                AddDataSeries(gcContract, BarsPeriodType.Minute, 15);   // idx 18

                // Map indices to (subfolder, ticker, timeframe, filename)
                seriesMap[1]  = ("micro", "MNQ", "1m",  "MNQ_1m.csv");
                seriesMap[2]  = ("micro", "MNQ", "5m",  "MNQ_5m.csv");
                seriesMap[3]  = ("micro", "MNQ", "15m", "MNQ_15m.csv");
                seriesMap[4]  = ("micro", "MES", "1m",  "MES_1m.csv");
                seriesMap[5]  = ("micro", "MES", "5m",  "MES_5m.csv");
                seriesMap[6]  = ("micro", "MES", "15m", "MES_15m.csv");
                seriesMap[7]  = ("micro", "MGC", "1m",  "MGC_1m.csv");
                seriesMap[8]  = ("micro", "MGC", "5m",  "MGC_5m.csv");
                seriesMap[9]  = ("micro", "MGC", "15m", "MGC_15m.csv");
                seriesMap[10] = ("mini",  "NQ",  "1m",  "NQ_1m.csv");
                seriesMap[11] = ("mini",  "NQ",  "5m",  "NQ_5m.csv");
                seriesMap[12] = ("mini",  "NQ",  "15m", "NQ_15m.csv");
                seriesMap[13] = ("mini",  "ES",  "1m",  "ES_1m.csv");
                seriesMap[14] = ("mini",  "ES",  "5m",  "ES_5m.csv");
                seriesMap[15] = ("mini",  "ES",  "15m", "ES_15m.csv");
                seriesMap[16] = ("mini",  "GC",  "1m",  "GC_1m.csv");
                seriesMap[17] = ("mini",  "GC",  "5m",  "GC_5m.csv");
                seriesMap[18] = ("mini",  "GC",  "15m", "GC_15m.csv");
            }
            else if (State == State.DataLoaded)
            {
                // Ensure output subdirectories exist
                string microDir = Path.Combine(OutputDirectory, "micro");
                string miniDir  = Path.Combine(OutputDirectory, "mini");
                if (!Directory.Exists(microDir))
                    Directory.CreateDirectory(microDir);
                if (!Directory.Exists(miniDir))
                    Directory.CreateDirectory(miniDir);
            }
        }

        protected override void OnBarUpdate()
        {
            int idx = BarsInProgress;

            // Skip the primary chart series (index 0)
            if (idx == 0 || !seriesMap.ContainsKey(idx))
                return;

            var (subfolder, ticker, tf, filename) = seriesMap[idx];
            string filePath = Path.Combine(OutputDirectory, subfolder, filename);

            // First call for this series: read last timestamp from existing file
            if (!initialized.Contains(idx))
            {
                initialized.Add(idx);
                DateTime lastTs = ReadLastTimestamp(filePath);
                lastWrittenTimestamp[idx] = lastTs;

                if (lastTs != DateTime.MinValue)
                {
                    Print(string.Format("CsvExporter: {0} resuming after {1}",
                        filename, lastTs.ToString("yyyy-MM-dd HH:mm:ss")));
                }
                else
                {
                    // New file — write header
                    File.WriteAllText(filePath, "datetime,open,high,low,close,volume\n");
                    Print(string.Format("CsvExporter: {0} starting fresh", filename));
                }
            }

            // Convert bar timestamp to US/Eastern
            DateTime barTime = Times[idx][0];
            DateTime easternTime = TimeZoneInfo.ConvertTime(barTime, easternZone);

            // Skip bars we already have (dedup on reboot/chart reload)
            if (easternTime <= lastWrittenTimestamp[idx])
                return;

            string timestamp = easternTime.ToString("yyyy-MM-dd HH:mm:ss");
            string line = string.Format("{0},{1},{2},{3},{4},{5}\n",
                timestamp,
                Opens[idx][0],
                Highs[idx][0],
                Lows[idx][0],
                Closes[idx][0],
                (long)Volumes[idx][0]);

            File.AppendAllText(filePath, line);
            lastWrittenTimestamp[idx] = easternTime;
        }

        /// <summary>
        /// Read the last timestamp from an existing CSV file.
        /// Returns DateTime.MinValue if file doesn't exist or is empty/header-only.
        /// </summary>
        private DateTime ReadLastTimestamp(string filePath)
        {
            if (!File.Exists(filePath))
                return DateTime.MinValue;

            try
            {
                // Read last non-empty line efficiently
                string lastLine = null;
                foreach (string line in File.ReadLines(filePath))
                {
                    if (!string.IsNullOrWhiteSpace(line) && !line.StartsWith("datetime"))
                        lastLine = line;
                }

                if (lastLine == null)
                    return DateTime.MinValue;

                // Parse the timestamp from first CSV column
                string tsStr = lastLine.Split(',')[0];
                DateTime parsed;
                if (DateTime.TryParse(tsStr, out parsed))
                    return parsed;
            }
            catch (Exception e)
            {
                Print(string.Format("CsvExporter: Could not read last timestamp from {0}: {1}",
                    filePath, e.Message));
            }

            return DateTime.MinValue;
        }

        /// <summary>
        /// Compute the current front-month contract name for a CME futures instrument.
        ///
        /// CME futures roll ~2 weeks before expiry (3rd Friday of contract month).
        /// We use a 2-week buffer: if we're within 14 days of the contract month,
        /// roll to the next contract.
        ///
        /// MNQ/MES/NQ/ES: quarterly (03, 06, 09, 12)
        /// MGC/GC:        bimonthly (02, 04, 06, 08, 10, 12)
        ///
        /// Returns NinjaTrader format: "MNQ 06-26", "GC 08-26", etc.
        /// </summary>
        private string GetFrontMonthContract(string symbol, bool isGold)
        {
            DateTime now = DateTime.Now;
            int[] monthNums = isGold ? GC_MONTH_NUMS : ES_NQ_MONTH_NUMS;

            for (int i = 0; i < monthNums.Length; i++)
            {
                int contractMonth = monthNums[i];
                int contractYear = now.Year;

                // Roll 14 days before contract month (approx 3rd Friday expiry)
                DateTime rollDate = new DateTime(contractYear, contractMonth, 14);

                if (now < rollDate)
                {
                    // NinjaTrader format: "SYMBOL MM-YY"
                    string monthStr = contractMonth.ToString("D2");
                    string yearStr = (contractYear % 100).ToString("D2");
                    return string.Format("{0} {1}-{2}", symbol, monthStr, yearStr);
                }
            }

            // Past all contracts this year — use first contract of next year
            int nextYear = now.Year + 1;
            string firstMonth = monthNums[0].ToString("D2");
            string nextYearStr = (nextYear % 100).ToString("D2");
            return string.Format("{0} {1}-{2}", symbol, firstMonth, nextYearStr);
        }
    }
}
