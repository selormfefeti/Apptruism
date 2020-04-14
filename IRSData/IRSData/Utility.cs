using CsvHelper;
using HtmlAgilityPack;
using Newtonsoft.Json.Linq;
using System;
using System.Collections.Generic;
using System.Dynamic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Xml;
using System.Xml.Linq;

namespace IRSData
{
    public static class Utility
    {
        private static string mbasePath = @"C:\Users\joefournier\Desktop\990Out";
        public static string DownloadWebContent(string URI)
        {
            string content = string.Empty;

            try
            {
                using (WebClient wc = new WebClient())
                {
                    content = wc.DownloadString(URI);
                }
            }
            catch
            {

            }

            return content;
        }

        public static JObject GetJObject(string URI)
        {
            return JObject.Parse(DownloadWebContent(URI));
        }

        public static XDocument GetXDocument(string URI)
        {
            XDocument xdoc = null;
            string cnt = DownloadWebContent(URI);

            if(!string.IsNullOrEmpty(cnt))
            {
                try
                {
                    if (cnt.IndexOf("<Return") != 0)
                    {
                        cnt = cnt.Substring(cnt.IndexOf('\n') + 1);
                    }

                    int i = cnt.IndexOf(" ");
                    int x = cnt.IndexOf('>');

                    string str = cnt.Substring(0, i).Trim();
                    string f = cnt.Substring(x, cnt.Length - x).Trim();

                    string xml = str + f;

                    var xmlReader = XmlReader.Create(new StringReader(xml));
                    xdoc = XDocument.Load(xmlReader);
                }
                catch(Exception ex)
                {
                    var test = ex;
                }

            }

            return xdoc;
        }

        internal static string FillClassification(string getClassificationPath)
        {
            string strClassification = string.Empty;
            var str = DownloadWebContent(getClassificationPath);

            try
            {
                HtmlDocument HTMLDoc = new HtmlDocument();
                HTMLDoc.LoadHtml(str);

                HtmlNodeCollection ClassificationNode = HTMLDoc.DocumentNode.SelectNodes("(//div[@class='profile-info'])//li");
                strClassification = ClassificationNode[1].ChildNodes[6].InnerHtml.Trim();
            }
            catch (Exception ex)
            {

            }

            return strClassification;
        }


        internal static void WriteFilingToCSV(IEnumerable<Filing> filings, int yr, string overwriteBasePath = null)
        {
            if (filings != null && filings.Count() > 0)
            {
                var basefiling = filings.ElementAt(0);
                if (!string.IsNullOrEmpty(overwriteBasePath))
                {
                    mbasePath = overwriteBasePath;
                }

                string fullName = string.Format(@"{0}\{1}.{2}.csv", mbasePath, yr, basefiling.FormType);

                if (File.Exists(fullName))
                {
                    File.Delete(fullName);
                }

                var records = new List<dynamic>();


                foreach (Filing filing in filings)
                {

                    dynamic record = new ExpandoObject();
                    record.EIN = filing.EIN;
                    record.TaxPeriod = filing.TaxPeriod;
                    record.DLN = filing.DLN;
                    record.FormType = filing.FormType;
                    record.URL = filing.URL;
                    record.OrganizationName = filing.OrganizationName;
                    record.SubmittedOn = filing.SubmittedOn;
                    record.ObjectId = filing.ObjectId;
                    record.LastUpdated = filing.LastUpdated;
                    record.Classification = filing.Classification;

                    if(filing.FormType990 != null)
                    {
                        AddFormTypeData<FormType990>(filing.FormType990, record);
                    }
                    else if(filing.FormType990EZ != null)
                    {
                        AddFormTypeData<FormType990EZ>(filing.FormType990EZ, record);
                    }

                    records.Add(record);
                }

                using (var writer = new StreamWriter(fullName))
                {
                    using (var csv = new CsvWriter(writer, CultureInfo.InvariantCulture))
                    {
                        csv.WriteRecords(records);
                    }
                }
            }
        }

        private static void AddFormTypeData<T>(T formType, dynamic record)
        {
            foreach (PropertyInfo propertyInfo in typeof(T).GetProperties())
            {
                try
                {
                    string propertyName = propertyInfo.Name;
                    var Value = typeof(T).GetProperty(propertyName).GetValue(formType, null);

                    (record as IDictionary<string, object>).Add(propertyName, Value);
                }
                catch (Exception ex)
                {

                }
            }
        }
    }
}
