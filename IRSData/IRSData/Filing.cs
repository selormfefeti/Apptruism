using Newtonsoft.Json.Linq;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Xml;
using System.Xml.Linq;
using System.Xml.XPath;

namespace IRSData
{
    public class Filing
    {
        private string cClassificationBasePath = @"https://projects.propublica.org/nonprofits/organizations/";

        public string EIN { get; set; }
        public string TaxPeriod { get; set; }
        public string DLN { get; set; }
        public string FormType { get; set; }
        public string URL { get; set; }
        public string OrganizationName { get; set; }
        public string SubmittedOn { get; set; }
        public string ObjectId { get; set; }
        public string LastUpdated { get; set; }

        public string Classification { get; set; }

        public FormType990 FormType990 { get; set; }

        public FormType990EZ FormType990EZ { get; set; }

        public bool IsFilingType
        {
            get
            {
                return this.FormType.Equals("990") || this.FormType.Equals("990EZ");

            }
        }

        public bool IsValid
        {
            get { return FormType990 != null || FormType990EZ != null; }
        }

        public string GetClassificationPath
        {
            get
            {
                return string.Concat(cClassificationBasePath, EIN);
            }
                
        }
        public Filing()
        {

        }
        public Filing(JToken filingData)
        {
            EIN = filingData["EIN"].ToString();
            TaxPeriod = filingData["TaxPeriod"].ToString();
            DLN = filingData["DLN"].ToString();
            FormType = filingData["FormType"].ToString();
            URL = filingData["URL"].ToString();
            OrganizationName = filingData["OrganizationName"].ToString();
            SubmittedOn = filingData["SubmittedOn"].ToString();
            ObjectId = filingData["ObjectId"].ToString();
            LastUpdated = filingData["LastUpdated"].ToString();
        }

        internal T FillFilingType<T>(XDocument xdoc)
        {
            T obj = (T)Activator.CreateInstance(typeof(T));
            foreach (PropertyInfo propertyInfo in typeof(T).GetProperties())
            {
                try
                {
                    string propertyName = propertyInfo.Name;
                    object[] attribute = propertyInfo.GetCustomAttributes(typeof(XPathAttibute), true);

                    if (attribute.Length > 0)
                    {
                        XPathAttibute myAttribute = (XPathAttibute)attribute[0];

                        string xPath = myAttribute.XPath + propertyName;

                        if (myAttribute.IsRepeating)
                        {
                            var values = xdoc.XPathSelectElements(xPath);
                            foreach (var value in values)
                            {
                                propertyInfo.SetValue(obj, value.Value, null);
                            }
                        }
                        else
                        {
                            string value = xdoc.XPathSelectElement(xPath).Value;
                            propertyInfo.SetValue(obj, value, null);
                        }
                    }
                }
                catch (Exception ex)
                {
                    var temp = ex;
                }
            }
            return obj;
        }

        internal void FillFormTypeData()
        {
            XDocument xdoc = Utility.GetXDocument(this.URL);
            if (xdoc != null)
            {
                if (FormType.Equals("990"))
                {
                    this.FormType990 = FillFilingType<FormType990>(xdoc);
                }
                else if(FormType.Equals("990EZ"))
                {
                    FormType990EZ = FillFilingType<FormType990EZ>(xdoc);
                }
            }
        }

        internal void FillClassification()
        {
            this.Classification = Utility.FillClassification(GetClassificationPath);
        }
    }
}
