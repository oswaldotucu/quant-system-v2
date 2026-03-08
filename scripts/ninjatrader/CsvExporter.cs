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
    /// Timestamps are in Eastern Time (NinjaTrader default for CME futures).
    ///
    /// NOTE: Update contract names (e.g., "MNQ 03-26") when contracts roll.
    ///       For continuous contracts, use "MNQ 00-00" syntax instead.
    /// </summary>
    public class CsvExporter : Indicator
    {
        // Maps BarsInProgress index -> (ticker, timeframe, filename)
        private Dictionary<int, (string Ticker, string Timeframe, string Filename)> seriesMap;
        private HashSet<int> headerWritten;

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

                // The primary series (BarsInProgress=0) is whatever chart this
                // indicator is added to. We add 8 more series below.
                // BarsInProgress indices 1-8 correspond to the added series.

                // MNQ
                AddDataSeries("MNQ 03-26", BarsPeriodType.Minute, 1);   // idx 1
                AddDataSeries("MNQ 03-26", BarsPeriodType.Minute, 5);   // idx 2
                AddDataSeries("MNQ 03-26", BarsPeriodType.Minute, 15);  // idx 3

                // MES
                AddDataSeries("MES 03-26", BarsPeriodType.Minute, 1);   // idx 4
                AddDataSeries("MES 03-26", BarsPeriodType.Minute, 5);   // idx 5
                AddDataSeries("MES 03-26", BarsPeriodType.Minute, 15);  // idx 6

                // MGC
                AddDataSeries("MGC 04-26", BarsPeriodType.Minute, 1);   // idx 7
                AddDataSeries("MGC 04-26", BarsPeriodType.Minute, 5);   // idx 8
                AddDataSeries("MGC 04-26", BarsPeriodType.Minute, 15);  // idx 9

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

            // Format timestamp as YYYY-MM-DD HH:mm:ss (Eastern Time)
            string timestamp = Times[idx][0].ToString("yyyy-MM-dd HH:mm:ss");
            string line = string.Format("{0},{1},{2},{3},{4},{5}\n",
                timestamp,
                Opens[idx][0],
                Highs[idx][0],
                Lows[idx][0],
                Closes[idx][0],
                (long)Volumes[idx][0]);

            File.AppendAllText(filePath, line);
        }
    }
}
