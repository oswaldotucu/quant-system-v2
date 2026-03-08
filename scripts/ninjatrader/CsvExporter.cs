#region Using declarations
using System;
using System.Collections.Generic;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// Exports OHLCV data for MNQ, MES, MGC across 1m, 5m, 15m timeframes
    /// to CSV files compatible with quant-system-v2.
    ///
    /// Usage:
    ///   1. Add this indicator to ANY chart (e.g., MNQ 1-minute)
    ///   2. Set OutputDirectory to your synced folder (Dropbox/OneDrive/etc.)
    ///   3. It subscribes to all 9 instrument/timeframe combos via AddDataSeries()
    ///   4. On chart load: writes all historical bars (backfill)
    ///   5. On each bar close: appends one line per series
    ///
    /// Output format (matches quant-system-v2 loader):
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
        // Maps BarsInProgress index -> (ticker, timeframe, filename)
        private Dictionary<int, (string Ticker, string Timeframe, string Filename)> seriesMap;
        private HashSet<int> headerWritten;
        private TimeZoneInfo easternZone;

        // CME quarterly roll months for MNQ/MES (H=Mar, M=Jun, U=Sep, Z=Dec)
        // CME bimonthly roll months for MGC (G=Feb, J=Apr, M=Jun, Q=Aug, V=Oct, Z=Dec)
        private static readonly char[] ES_NQ_MONTHS = { 'H', 'M', 'U', 'Z' };
        private static readonly int[]  ES_NQ_MONTH_NUMS = { 3, 6, 9, 12 };
        private static readonly char[] GC_MONTHS = { 'G', 'J', 'M', 'Q', 'V', 'Z' };
        private static readonly int[]  GC_MONTH_NUMS = { 2, 4, 6, 8, 10, 12 };

        [NinjaScriptProperty]
        [Display(Name = "Output Directory", Description = "Folder for CSV output",
                 Order = 1, GroupName = "Parameters")]
        public string OutputDirectory { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Exports OHLCV to CSV for quant-system-v2";
                Name = "CsvExporter";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                OutputDirectory = @"C:\NtExport";
            }
            else if (State == State.Configure)
            {
                seriesMap = new Dictionary<int, (string, string, string)>();
                headerWritten = new HashSet<int>();
                easternZone = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

                // Resolve current front-month contracts dynamically
                string mnqContract = GetFrontMonthContract("MNQ", false);
                string mesContract = GetFrontMonthContract("MES", false);
                string mgcContract = GetFrontMonthContract("MGC", true);

                Print(string.Format("CsvExporter: MNQ={0}, MES={1}, MGC={2}",
                    mnqContract, mesContract, mgcContract));

                // The primary series (BarsInProgress=0) is whatever chart this
                // indicator is added to. We add 9 more series below.

                // MNQ
                AddDataSeries(mnqContract, BarsPeriodType.Minute, 1);   // idx 1
                AddDataSeries(mnqContract, BarsPeriodType.Minute, 5);   // idx 2
                AddDataSeries(mnqContract, BarsPeriodType.Minute, 15);  // idx 3

                // MES
                AddDataSeries(mesContract, BarsPeriodType.Minute, 1);   // idx 4
                AddDataSeries(mesContract, BarsPeriodType.Minute, 5);   // idx 5
                AddDataSeries(mesContract, BarsPeriodType.Minute, 15);  // idx 6

                // MGC
                AddDataSeries(mgcContract, BarsPeriodType.Minute, 1);   // idx 7
                AddDataSeries(mgcContract, BarsPeriodType.Minute, 5);   // idx 8
                AddDataSeries(mgcContract, BarsPeriodType.Minute, 15);  // idx 9

                // Map indices to filenames
                // NOTE: Index 0 is the primary chart series — we skip it
                seriesMap[1] = ("MNQ", "1m",  "MNQ_1m.csv");
                seriesMap[2] = ("MNQ", "5m",  "MNQ_5m.csv");
                seriesMap[3] = ("MNQ", "15m", "MNQ_15m.csv");
                seriesMap[4] = ("MES", "1m",  "MES_1m.csv");
                seriesMap[5] = ("MES", "5m",  "MES_5m.csv");
                seriesMap[6] = ("MES", "15m", "MES_15m.csv");
                seriesMap[7] = ("MGC", "1m",  "MGC_1m.csv");
                seriesMap[8] = ("MGC", "5m",  "MGC_5m.csv");
                seriesMap[9] = ("MGC", "15m", "MGC_15m.csv");
            }
            else if (State == State.DataLoaded)
            {
                // Ensure output directory exists
                if (!Directory.Exists(OutputDirectory))
                    Directory.CreateDirectory(OutputDirectory);
            }
        }

        protected override void OnBarUpdate()
        {
            int idx = BarsInProgress;

            // Skip the primary chart series (index 0)
            if (idx == 0 || !seriesMap.ContainsKey(idx))
                return;

            var (ticker, tf, filename) = seriesMap[idx];
            string filePath = Path.Combine(OutputDirectory, filename);

            // Write header on first bar
            if (!headerWritten.Contains(idx))
            {
                // Overwrite file with header (clean start on chart load)
                File.WriteAllText(filePath, "datetime,open,high,low,close,volume\n");
                headerWritten.Add(idx);
            }

            // Convert timestamp to US/Eastern regardless of NT's configured timezone
            DateTime barTime = Times[idx][0];
            DateTime easternTime = TimeZoneInfo.ConvertTime(barTime, easternZone);
            string timestamp = easternTime.ToString("yyyy-MM-dd HH:mm:ss");

            string line = string.Format("{0},{1},{2},{3},{4},{5}\n",
                timestamp,
                Opens[idx][0],
                Highs[idx][0],
                Lows[idx][0],
                Closes[idx][0],
                (long)Volumes[idx][0]);

            File.AppendAllText(filePath, line);
        }

        /// <summary>
        /// Compute the current front-month contract name for a CME futures instrument.
        ///
        /// CME futures roll ~2 weeks before expiry (3rd Friday of contract month).
        /// We use a 2-week buffer: if we're within 14 days of the contract month,
        /// roll to the next contract.
        ///
        /// MNQ/MES: quarterly (H=Mar, M=Jun, U=Sep, Z=Dec)
        /// MGC:     bimonthly (G=Feb, J=Apr, M=Jun, Q=Aug, V=Oct, Z=Dec)
        /// </summary>
        private string GetFrontMonthContract(string symbol, bool isGold)
        {
            DateTime now = DateTime.Now;
            int[] monthNums = isGold ? GC_MONTH_NUMS : ES_NQ_MONTH_NUMS;
            char[] monthCodes = isGold ? GC_MONTHS : ES_NQ_MONTHS;

            for (int i = 0; i < monthNums.Length; i++)
            {
                int contractMonth = monthNums[i];
                int contractYear = now.Year;

                // Contract expiry is approximately 3rd Friday of the contract month.
                // Roll 14 days before: if now < (contract month, day 1) we're safe;
                // if now is in the contract month but before the 14th, still use it.
                DateTime rollDate = new DateTime(contractYear, contractMonth, 14);

                if (now < rollDate)
                {
                    // This contract is still active
                    string yearStr = (contractYear % 100).ToString("D2");
                    return string.Format("{0} {1}-{2}", symbol, monthCodes[i], yearStr);
                }
            }

            // Past all contracts this year — use first contract of next year
            int nextYear = now.Year + 1;
            string nextYearStr = (nextYear % 100).ToString("D2");
            return string.Format("{0} {1}-{2}", symbol, monthCodes[0], nextYearStr);
        }
    }
}
