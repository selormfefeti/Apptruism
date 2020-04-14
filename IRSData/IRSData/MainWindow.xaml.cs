using CsvHelper;
using HtmlAgilityPack;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Navigation;
using System.Windows.Shapes;
using System.Xml;
using System.Xml.Linq;
using System.Xml.Serialization;
using System.Xml.XPath;

namespace IRSData
{
    /// <summary>
    /// Interaction logic for MainWindow.xaml
    /// </summary>
    public partial class MainWindow : Window
    {
        private Dictionary<int, List<Filing>> yrFilings;

        public MainWindow()
        {
            InitializeComponent();
        }

        private void run_Click(object sender, RoutedEventArgs e)
        {
           yrFilings = GetIRS1099Data();
        }

        private Dictionary<int, List<Filing>> GetIRS1099Data(int seed = 2019, int maxDate = 2019)
        {
            Dictionary<int, List<Filing>> yrFilings = new Dictionary<int, List<Filing>>();
            int curYr = seed;

            while(curYr <= maxDate)
            {
                List<Filing> curFilings = GetFilings(curYr);
                yrFilings[curYr] = curFilings;
                curYr++;
            }

            return yrFilings;
        }

        private List<Filing> GetFilings(int curYr)
        {
            List<Filing> curYrFilings = new List<Filing>();
            var JobjfilingsRoot = Utility.GetJObject(string.Format(@"https://s3.amazonaws.com/irs-form-990/index_{0}.json", curYr));

            var filings = JobjfilingsRoot[string.Format("Filings{0}", curYr)].Children();

            foreach (JToken filingData in filings)
            {
                Filing curFiling = new Filing(filingData);
                if (curFiling.IsFilingType)
                {
                    curFiling.FillFormTypeData();
                    curFiling.FillClassification();

                    if (curFiling.IsValid)
                    {
                        curYrFilings.Add(curFiling);
                    }
                }


                if(curYrFilings.Count % 20000 == 0)
                {
                    this.yrFilings[curYr] = curYrFilings;
                    WriteFilings();
                }

            }

            return curYrFilings;
        }

        private void runlocal_Click(object sender, RoutedEventArgs e)
        {
            if (yrFilings == null)
            {
                yrFilings = GetIRS1099Data();
            }

            WriteFilings();

        }

        private void WriteFilings()
        {
            foreach (var yr990s in yrFilings)
            {
                var FormType990s = yr990s.Value.Where(x => x.FormType990 != null);
                if (FormType990s != null)
                {
                    Utility.WriteFilingToCSV(FormType990s, yr990s.Key);
                }

                var FormType990EZs = yr990s.Value.Where(x => x.FormType990EZ != null);
                if (FormType990EZs != null)
                {
                    Utility.WriteFilingToCSV(FormType990EZs, yr990s.Key);
                }
            }
        }

        private void test()
        {
            string xml = File.ReadAllText(@"C:\Users\joefournier\Desktop\test.xml");

            var xmlReader = new StringReader(xml);
            var xdoc = XDocument.Load(xmlReader);

            Filing f = new Filing();
            f.EIN = "454824300";
            f.DLN = "joeDLN";
            f.FormType = "990EZ";
            f.ObjectId = "0011";
            f.LastUpdated = DateTime.Now.ToString();
            f.TaxPeriod = "Joe Now";
            f.SubmittedOn = f.LastUpdated;
            f.OrganizationName = "joe Pimp";
            f.URL = "URL";


            f.FormType990 = f.FillFilingType<FormType990>(xdoc);
            f.FillClassification();

            List<Filing> fl = new List<Filing>();
            fl.Add(f);

            Utility.WriteFilingToCSV(fl, 2019);

        }
    }
}
