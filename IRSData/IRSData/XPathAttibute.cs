using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace IRSData
{
    class XPathAttibute : Attribute
    {
        private string xPath;
        private bool misRepeating;

        public XPathAttibute(string xPath, bool isRepeating = false)
        {
            this.xPath = xPath;
            this.misRepeating = isRepeating;
        }

        public string XPath
        {
            get
            {
                return xPath;
            }

            set
            {
                xPath = value;
            }
        }

        public bool IsRepeating
        {
            get
            {
                return misRepeating;
            }

            set
            {
                misRepeating = value;
            }
        }
    }
}
